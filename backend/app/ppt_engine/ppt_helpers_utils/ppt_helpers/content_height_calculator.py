"""
Content-Based Height Calculator

Unified height calculation utilities for all elements (tables, charts, etc.)
that account for actual content, text wrapping, and all height components
(section titles, labels, content, sources).

This module provides consistent height calculations across both the assigning
and rendering phases, eliminating discrepancies that lead to unnecessary
row trimming and incorrect layout assignments.
"""

import os
from typing import List, Dict, Any, Tuple, Optional, Set
import re

# Enable verbose calibration logging via environment variable
# Set CALIBRATION_DEBUG=1 to see detailed per-row breakdown
CALIBRATION_DEBUG = os.environ.get("CALIBRATION_DEBUG", "0") == "1"


def _log_calibration(message: str):
    """Print calibration debug message if CALIBRATION_DEBUG is enabled."""
    if CALIBRATION_DEBUG:
        print(message)


def _is_numeric_value(value: Any) -> bool:
    """Check if value is numeric by stripping formatting and parsing.
    
    Handles:
    - Formatted numbers like "1,234,567"
    - Negative numbers like "(1,234)"
    - Percentages like "35.3%"
    - Currency like "$1,234" or "$ 46.85"
    """
    if value is None:
        return False
    s = str(value).strip()
    if not s:
        return False
    # Handle accounting-style negatives: (1,234) -> -1234
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    # Strip common formatting: commas, percent signs, dollar signs, spaces
    s = s.replace(",", "").replace("%", "").replace("$", "").replace(" ", "")
    # Handle empty string after stripping
    if not s:
        return False
    # Try to parse as float
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _get_column_max_length(
    data: List[Dict[str, Any]],
    col_name: str,
    has_header: bool,
    include_header_in_max: bool = True,
) -> int:
    """Get the maximum character length of values in a column.
    
    Args:
        data: Table data
        col_name: Column name
        has_header: Whether table has header row
        include_header_in_max: If True, include header text in max calculation.
                               If False, only consider data values.
    """
    max_len = 0
    if has_header and include_header_in_max:
        max_len = len(str(col_name))
    for row_data in data:
        cell_text = str(row_data.get(col_name, ""))
        max_len = max(max_len, len(cell_text))
    return max_len


def _get_column_max_data_length(
    data: List[Dict[str, Any]],
    col_name: str,
) -> int:
    """Get the maximum character length of DATA values only (excludes header)."""
    max_len = 0
    for row_data in data:
        cell_text = str(row_data.get(col_name, ""))
        max_len = max(max_len, len(cell_text))
    return max_len


def _is_numeric_column(data: List[Dict[str, Any]], col_name: str) -> bool:
    """Check if ALL values in a column are numeric."""
    if not data:
        return False
    for row_data in data:
        value = row_data.get(col_name, "")
        if value is None or str(value).strip() == "":
            continue  # Skip empty values
        if not _is_numeric_value(value):
            return False
    return True


def calculate_column_widths(
    data: List[Dict[str, Any]],
    table_width: float,
    element_dims: Any,
    columns: List[str],
    has_header: bool = True,
) -> List[float]:
    """
    Calculate column widths with strict priority-based allocation.

    PRIORITY ORDER (strictly enforced):
    1. FIRST PRIORITY: Reserve space for col 1 & col 2 (indices 0 and 1) to NOT wrap
       - Calculate width needed for longest DATA content in each column
       - Headers CAN wrap; only data content is protected
    2. SECOND PRIORITY: Distribute remaining space to col 3+ (indices 2+) based on wrap scores
       - Columns with more content that would wrap get proportionally more space
    3. LAST RESORT: If any column is below minimum AND no other option exists,
       reduce col 1 (then col 2) to word-minimum (width needed for longest single word)

    Args:
        data: Table data (list of dictionaries)
        table_width: Available width for the table in inches
        element_dims: ElementDimensions config object
        columns: List of column names to use
        has_header: Whether table has header row

    Returns:
        List of column widths in inches
    """
    num_columns = len(columns)

    if num_columns == 0:
        return []

    if num_columns == 1:
        # Single column takes full width
        return [table_width]

    # Get configuration parameters from ElementDimensions
    font_size_pt = element_dims.table_font_size

    # Character width for column WIDTH calculation (text columns)
    char_width_ratio = element_dims.table_char_width_ratio_for_column_width
    char_width_inches = (font_size_pt * char_width_ratio) / 72.0
    
    # Character width for NUMERIC columns (more generous to prevent wrapping)
    numeric_char_width_ratio = char_width_ratio * 1.35  # 35% wider for numeric columns
    numeric_char_width_inches = (font_size_pt * numeric_char_width_ratio) / 72.0

    # Cell horizontal margins (PowerPoint default is ~0.05" on each side = 0.10" total)
    # This accounts for padding inside table cells that reduces available text width
    cell_h_margin_inches = 0.10

    # Safety factor for column width (accounts for font rendering variations)
    width_safety_factor = element_dims.table_first_col_width_safety_factor

    # Numeric column no-wrap configuration
    numeric_no_wrap_enabled = getattr(
        element_dims, "table_numeric_column_no_wrap_enabled", True
    )
    numeric_max_chars = getattr(
        element_dims, "table_numeric_column_max_chars_no_wrap", 14
    )
    
    # Configuration for protected columns (columns 1 & 2 by default)
    # These columns should not wrap their data
    protected_column_count = getattr(
        element_dims, "table_protected_column_count", 2
    )

    # =========================================================================
    # ALGORITHM (2026-02-03 Update):
    # PRIORITY ORDER:
    # 1. Reserve space for col 1 & col 2 to NOT wrap (calculate width for longest DATA)
    # 2. Distribute remaining space to col 3+ based on wrap scores
    # 3. LAST RESORT: If any col is below minimum, reduce col 1 to word-minimum
    # =========================================================================
    
    absolute_min = 0.30  # Hard minimum for any column
    
    # --- STEP 1: Calculate DATA-BASED minimum for ALL columns ---
    # HEADERS ARE IGNORED - only DATA values determine minimum widths
    # This ensures data never wraps for protected columns, but headers can wrap freely
    
    # Track which columns are numeric (can shrink after "wrappable" cols)
    numeric_cols: Set[int] = set()
    # Track data-min for all columns
    data_min_widths: Dict[int, float] = {}  # col_idx -> min_width for DATA not to wrap
    
    for col_idx, col_name in enumerate(columns):
        max_data_len = _get_column_max_data_length(data, col_name)
        
        # Check if this is a numeric column
        is_numeric = _is_numeric_column(data, col_name)
        if is_numeric:
            numeric_cols.add(col_idx)
        
        # Calculate data-min for this column (width needed for DATA not to wrap)
        if is_numeric and numeric_no_wrap_enabled and max_data_len <= numeric_max_chars:
            # Protected numeric: width based on data length (use wider ratio for numeric)
            text_width = max_data_len * numeric_char_width_inches
            data_min = max(absolute_min, text_width + cell_h_margin_inches)
        else:
            # Non-numeric or big-value: use absolute minimum (can wrap more)
            data_min = absolute_min
        
        data_min_widths[col_idx] = data_min
    
    # For compatibility
    numeric_min_widths = {i: data_min_widths[i] for i in numeric_cols if i in data_min_widths}
    
    # --- STEP 2: Calculate widths for PROTECTED columns (columns 1 & 2) ---
    # Protected columns are columns 0 and 1 (first two columns)
    # THREE tiers of width for protected columns:
    #   1. ideal_width: BOTH header AND data won't wrap (best case)
    #   2. data_only_width: only DATA won't wrap (headers can wrap if needed)
    #   3. word_min_width: longest word won't break mid-word (last resort)
    
    protected_col_ideal_widths: Dict[int, float] = {}      # Header + data won't wrap
    protected_col_data_only_widths: Dict[int, float] = {}  # Only data won't wrap
    protected_col_min_widths: Dict[int, float] = {}        # Word minimum (last resort)
    
    for col_idx in range(min(protected_column_count, num_columns)):
        col_name = columns[col_idx]
        
        # Calculate data length and header length separately
        max_data_len = _get_column_max_data_length(data, col_name)
        header_len = len(str(col_name))
        
        # For NUMERIC columns in protected range: still need to consider header length
        # The numeric column already has data-min calculated, but we need to check if header is longer
        if col_idx in numeric_cols:
            numeric_data_width = data_min_widths.get(col_idx, absolute_min)
            # Calculate header-based width
            header_width = max(
                absolute_min,
                (header_len * char_width_inches * width_safety_factor) + cell_h_margin_inches
            )
            # Ideal = max of numeric data width and header width
            protected_col_ideal_widths[col_idx] = max(numeric_data_width, header_width)
            protected_col_data_only_widths[col_idx] = numeric_data_width
            protected_col_min_widths[col_idx] = numeric_data_width
            continue
        
        # TIER 1: Ideal width = BOTH header AND data won't wrap
        max_content_len = max(max_data_len, header_len)
        ideal_width = max(
            absolute_min,
            (max_content_len * char_width_inches * width_safety_factor) + cell_h_margin_inches
        )
        
        # TIER 2: Data-only width = only DATA won't wrap (headers can wrap)
        # Use minimal safety factor (1.0) for protected columns - tight fit to save space
        protected_safety_factor = 1.0
        data_only_width = max(
            absolute_min,
            (max_data_len * char_width_inches * protected_safety_factor) + cell_h_margin_inches
        )
        
        # TIER 3: Word minimum = longest word won't break mid-word (last resort)
        max_word_len = 0
        # Check header words
        for word in str(col_name).split():
            max_word_len = max(max_word_len, len(word))
        # Check data words
        for row_data in data:
            cell_text = str(row_data.get(col_name, ""))
            for word in cell_text.split():
                max_word_len = max(max_word_len, len(word))
        word_min_width = max(
            absolute_min,
            (int(max_word_len * 1.1) * char_width_inches * width_safety_factor) + cell_h_margin_inches
        )
        
        # Cap widths at reasonable percentages of table width
        if col_idx == 0:
            ideal_width = min(ideal_width, table_width * 0.40)
            data_only_width = min(data_only_width, table_width * 0.35)
            word_min_width = min(word_min_width, table_width * 0.30)
        else:
            ideal_width = min(ideal_width, table_width * 0.35)
            data_only_width = min(data_only_width, table_width * 0.30)
            word_min_width = min(word_min_width, table_width * 0.25)
        
        protected_col_ideal_widths[col_idx] = ideal_width
        protected_col_data_only_widths[col_idx] = data_only_width
        protected_col_min_widths[col_idx] = word_min_width
        
        # Update data_min for protected column (used in shrink priority)
        data_min_widths[col_idx] = word_min_width
    
    # --- STEP 3: Initial allocation - protected columns get data-only width ---
    # Rule: Col 1 & 2 DATA should NEVER wrap, but headers CAN wrap if needed
    # This gives more space to other columns while protecting the data
    column_widths: List[float] = [0.0] * num_columns
    
    # Find "other" columns (indices >= protected_column_count)
    other_col_indices = [i for i in range(protected_column_count, num_columns)]
    
    # Calculate remaining space after protected columns get their data-only width
    protected_total_needed = sum(protected_col_data_only_widths.get(i, absolute_min) 
                                  for i in range(min(protected_column_count, num_columns)))
    remaining_for_others = table_width - protected_total_needed
    
    # Debug: show column analysis
    protected_debug = {str(columns[i])[:15]: f"data_only={protected_col_data_only_widths.get(i, 0):.2f}, word_min={protected_col_min_widths.get(i, 0):.2f}" 
                       for i in range(min(protected_column_count, num_columns))}
    print(f"    DEBUG: Protected cols (1&2) = {protected_debug}")
    print(f"    DEBUG: remaining_for_others={remaining_for_others:.3f}, num_other_cols={len(other_col_indices)}")
    
    # ALWAYS use data-only width for protected columns
    # Rule: Col 1 & 2 DATA should NEVER wrap, but headers CAN wrap if needed
    # This gives more space to other columns while protecting the data
    
    # Allocate protected columns with data-only width (headers can wrap)
    for col_idx in range(min(protected_column_count, num_columns)):
        column_widths[col_idx] = protected_col_data_only_widths.get(col_idx, absolute_min)
    
    # Calculate remaining width for cols 3+
    protected_total = sum(column_widths[i] for i in range(min(protected_column_count, num_columns)))
    remaining = table_width - protected_total
    
    print(f"    DEBUG: Protected cols allocated {protected_total:.3f}\" (data-only), remaining for cols 3+: {remaining:.3f}\"")
    
    # PRIORITY 2: Distribute remaining space to cols 3+ based on WRAP SCORES
    if other_col_indices:
        # Calculate wrap score for each "other" column at minimum width
        def calc_initial_wrap_score(col_idx: int) -> float:
            """Calculate how much content would wrap at minimum width."""
            col_name = columns[col_idx]
            max_data_len = _get_column_max_data_length(data, col_name)
            header_len = len(str(col_name))
            
            min_chars_per_line = max(1, int((absolute_min - cell_h_margin_inches) / char_width_inches))
            data_lines = max(1, max_data_len / min_chars_per_line) if min_chars_per_line > 0 else 1
            header_lines = max(1, header_len / min_chars_per_line) if min_chars_per_line > 0 else 1
            
            return max(0, data_lines - 1) + max(0, header_lines - 1)
        
        # Calculate wrap scores for allocation
        initial_wrap_scores = {i: calc_initial_wrap_score(i) for i in other_col_indices}
        total_wrap_score = sum(initial_wrap_scores.values())
        
        print(f"    DEBUG: Wrap scores for cols 3+: {initial_wrap_scores}")
        
        if remaining > 0:
            if total_wrap_score > 0:
                # Distribute proportionally based on wrap scores
                for col_idx in other_col_indices:
                    proportion = initial_wrap_scores[col_idx] / total_wrap_score
                    column_widths[col_idx] = max(absolute_min, remaining * proportion)
            else:
                # All columns have zero wrap score - distribute equally
                equal_share = remaining / len(other_col_indices)
                for col_idx in other_col_indices:
                    column_widths[col_idx] = max(absolute_min, equal_share)
        else:
            # No remaining space - give minimum to other columns
            for col_idx in other_col_indices:
                column_widths[col_idx] = absolute_min
    
    # For backward compatibility
    wrappable_indices = other_col_indices
    
    # Debug: show column names and widths
    col_debug = [(str(columns[i])[:20], f"{column_widths[i]:.2f}", 
                  "P" if i < protected_column_count else "W") 
                 for i in range(num_columns)]
    print(f"    DEBUG STEP 3: total={sum(column_widths):.3f}, table_width={table_width:.3f}")
    print(f"    DEBUG COLS: {col_debug}")
    
    # --- STEP 4: Handle over-allocation ---
    # SHRINK PRIORITY (cols 1&2 have HIGHEST priority - last to shrink):
    # 1. Shrink cols 3+ (wrappable) to absolute_min FIRST
    # 2. Shrink col 2 to data-only width (headers can wrap, data won't)
    # 3. Shrink col 1 to data-only width (headers can wrap, data won't)
    # 4. Shrink col 2 to word-minimum
    # 5. LAST RESORT: Shrink col 1 to word-minimum
    # 6. Emergency: Scale all proportionally
    total = sum(column_widths)
    if total > table_width:
        excess = total - table_width
        print(f"    DEBUG STEP 4: Over-allocated by {excess:.3f}\", need to shrink")
        
        # Step 4a: Shrink cols 3+ (wrappable columns) to absolute_min FIRST
        if wrappable_indices and excess > 0:
            wrappable_total = sum(column_widths[i] for i in wrappable_indices)
            wrappable_reducible = wrappable_total - (absolute_min * len(wrappable_indices))
            if wrappable_reducible > 0:
                take = min(excess, wrappable_reducible)
                if wrappable_total > 0:
                    scale = (wrappable_total - take) / wrappable_total
                    for i in wrappable_indices:
                        column_widths[i] = max(absolute_min, column_widths[i] * scale)
                excess -= take
                print(f"    DEBUG STEP 4a: Shrunk cols 3+, took {take:.3f}\", excess now {excess:.3f}\"")
        
        # Step 4b: Shrink col 2 (index 1) to data-only width (headers can wrap)
        if excess > 0 and num_columns > 1 and 1 not in numeric_cols:
            col_1_current = column_widths[1]
            col_1_data_only = protected_col_data_only_widths.get(1, absolute_min)
            col_1_reducible = col_1_current - col_1_data_only
            
            if col_1_reducible > 0:
                take = min(excess, col_1_reducible)
                column_widths[1] -= take
                excess -= take
                print(f"    DEBUG STEP 4b: Shrunk col 2 to data-only ({col_1_data_only:.3f}\"), took {take:.3f}\"")
        
        # Step 4c: Shrink col 1 (index 0) to data-only width (headers can wrap)
        if excess > 0 and num_columns > 0 and 0 not in numeric_cols:
            col_0_current = column_widths[0]
            col_0_data_only = protected_col_data_only_widths.get(0, absolute_min)
            col_0_reducible = col_0_current - col_0_data_only
            
            if col_0_reducible > 0:
                take = min(excess, col_0_reducible)
                column_widths[0] -= take
                excess -= take
                print(f"    DEBUG STEP 4c: Shrunk col 1 to data-only ({col_0_data_only:.3f}\"), took {take:.3f}\"")
        
        # Step 4d: Shrink col 2 (index 1) to word-minimum
        if excess > 0 and num_columns > 1 and 1 not in numeric_cols:
            col_1_current = column_widths[1]
            col_1_word_min = protected_col_min_widths.get(1, absolute_min)
            col_1_reducible = col_1_current - col_1_word_min
            
            if col_1_reducible > 0:
                take = min(excess, col_1_reducible)
                column_widths[1] -= take
                excess -= take
                print(f"    DEBUG STEP 4d: Shrunk col 2 to word-min ({col_1_word_min:.3f}\"), took {take:.3f}\"")
        
        # Step 4e: LAST RESORT - Shrink col 1 (index 0) to word-minimum
        if excess > 0 and num_columns > 0 and 0 not in numeric_cols:
            col_0_current = column_widths[0]
            col_0_word_min = protected_col_min_widths.get(0, absolute_min)
            col_0_reducible = col_0_current - col_0_word_min
            
            if col_0_reducible > 0:
                take = min(excess, col_0_reducible)
                column_widths[0] -= take
                excess -= take
                print(f"    ⚠️ LAST RESORT: Shrunk col 1 to word-min ({col_0_word_min:.3f}\"), took {take:.3f}\"")
        
        # Step 4f: If STILL over, shrink protected columns below word-min to absolute_min
        if excess > 0.01:
            for col_idx in range(min(protected_column_count, num_columns)):
                if excess <= 0:
                    break
                reducible = column_widths[col_idx] - absolute_min
                if reducible > 0:
                    take = min(excess, reducible)
                    column_widths[col_idx] -= take
                    excess -= take
                    print(f"    ⚠️ EMERGENCY: Protected col {col_idx} shrunk to {column_widths[col_idx]:.3f}\"")
        
        # Step 4g: If STILL over, scale all proportionally (data will wrap everywhere)
        if excess > 0.01:
            scale = table_width / sum(column_widths)
            column_widths = [w * scale for w in column_widths]
            print("    ⚠️ WARNING: All columns scaled to fit - some data may wrap")
    
    # --- STEP 5: Optimize cols 3+ (wrappable) - minimize wrapping by redistributing ---
    # Move width from least-wrapped to most-wrapped columns within cols 3+
    # Protected columns (1 & 2) are NOT touched in this optimization
    
    def calc_wrap_score(col_idx: int, width: float) -> float:
        """Calculate wrapping score: excess lines for header + data at given width."""
        col_name = columns[col_idx]
        usable = max(0.1, width - cell_h_margin_inches)
        
        # Header wrapping (headers are bolder, use wider char width)
        header_char_width = char_width_inches * 1.2
        header_len = len(str(col_name))
        header_cpl = usable / header_char_width if header_char_width > 0 else 10
        header_lines = max(1, header_len / header_cpl) if header_cpl > 0 else 1
        header_excess = max(0, header_lines - 1)
        
        # Data wrapping
        max_data_len = _get_column_max_data_length(data, col_name)
        data_cpl = usable / char_width_inches if char_width_inches > 0 else 10
        data_lines = max(1, max_data_len / data_cpl) if data_cpl > 0 else 1
        data_excess = max(0, data_lines - 1)
        
        return header_excess + data_excess
    
    # Iteratively optimize: move width from least-wrapped to most-wrapped in cols 3+
    print(f"    DEBUG STEP 5: Starting optimization, widths before: {[f'{w:.2f}' for w in column_widths]}")
    
    # Only optimize cols 3+ (wrappable columns)
    if len(wrappable_indices) > 1:
        for iteration in range(20):  # More iterations for better convergence
            # Calculate wrap scores for cols 3+ only
            wrap_scores: Dict[int, float] = {}
            for col_idx in wrappable_indices:
                wrap_scores[col_idx] = calc_wrap_score(col_idx, column_widths[col_idx])
            
            if not wrap_scores:
                break
            
            # Find most-wrapped column (candidate to RECEIVE width)
            most_wrapped_idx = max(wrap_scores, key=wrap_scores.get)  # type: ignore
            
            # Find least-wrapped column that can GIVE width
            sorted_by_wrap = sorted(wrap_scores.items(), key=lambda x: x[1])
            
            least_wrapped_idx = -1
            available_to_give = 0.0
            for col_idx, score in sorted_by_wrap:
                if col_idx == most_wrapped_idx:
                    continue
                available = column_widths[col_idx] - absolute_min
                if available > 0.02:
                    least_wrapped_idx = col_idx
                    available_to_give = available
                    break
            
            if least_wrapped_idx < 0:
                break  # No column can give width
            
            # If difference is small, stop optimizing
            score_diff = wrap_scores[most_wrapped_idx] - wrap_scores[least_wrapped_idx]
            if score_diff < 0.1:
                break
            
            # Transfer width proportional to score difference
            transfer_ratio = min(0.5, score_diff / 5.0)
            transfer = min(0.5, available_to_give * transfer_ratio)
            transfer = max(0.02, transfer)
            
            column_widths[least_wrapped_idx] -= transfer
            column_widths[most_wrapped_idx] += transfer
    
    # --- STEP 6: Normalize to match table_width exactly ---
    # SHRINK PRIORITY (cols 1&2 have HIGHEST priority - last to shrink):
    # 1. Cols 3+ (wrappable) - shrink to absolute_min FIRST
    # 2. Col 2 - shrink to data-only (headers can wrap)
    # 3. Col 1 - shrink to data-only (headers can wrap)
    # 4. Col 2 - shrink to word-minimum
    # 5. Col 1 - shrink to word-minimum (LAST RESORT)
    # 6. Scale all proportionally (emergency)
    
    current_sum = sum(column_widths)
    
    if current_sum > table_width:
        excess = current_sum - table_width
        
        print(f"    DEBUG STEP 6: Need to shrink by {excess:.3f}\"")
        
        # Step 6a: Shrink cols 3+ to absolute_min FIRST
        if wrappable_indices and excess > 0:
            wrappable_total = sum(column_widths[i] for i in wrappable_indices)
            wrappable_reducible = wrappable_total - (absolute_min * len(wrappable_indices))
            if wrappable_reducible > 0:
                take = min(excess, wrappable_reducible)
                if wrappable_total > 0:
                    scale = (wrappable_total - take) / wrappable_total
                    for i in wrappable_indices:
                        column_widths[i] = max(absolute_min, column_widths[i] * scale)
                excess -= take
        
        # Step 6b: Shrink col 2 to data-only (headers can wrap)
        if excess > 0 and num_columns > 1 and 1 not in numeric_cols:
            col_1_data_only = protected_col_data_only_widths.get(1, absolute_min)
            reducible = column_widths[1] - col_1_data_only
            if reducible > 0:
                take = min(excess, reducible)
                column_widths[1] -= take
                excess -= take
        
        # Step 6c: Shrink col 1 to data-only (headers can wrap)
        if excess > 0 and num_columns > 0 and 0 not in numeric_cols:
            col_0_data_only = protected_col_data_only_widths.get(0, absolute_min)
            reducible = column_widths[0] - col_0_data_only
            if reducible > 0:
                take = min(excess, reducible)
                column_widths[0] -= take
                excess -= take
        
        # Step 6d: Shrink col 2 to word-minimum
        if excess > 0 and num_columns > 1 and 1 not in numeric_cols:
            col_1_word_min = protected_col_min_widths.get(1, absolute_min)
            reducible = column_widths[1] - col_1_word_min
            if reducible > 0:
                take = min(excess, reducible)
                column_widths[1] -= take
                excess -= take
        
        # Step 6e: LAST RESORT - Shrink col 1 to word-minimum
        if excess > 0 and num_columns > 0 and 0 not in numeric_cols:
            col_0_word_min = protected_col_min_widths.get(0, absolute_min)
            reducible = column_widths[0] - col_0_word_min
            if reducible > 0:
                take = min(excess, reducible)
                column_widths[0] -= take
                excess -= take
                print(f"    ⚠️ LAST RESORT: Shrunk col 1 to word-min ({col_0_word_min:.3f}\")")
        
        # Step 6f: Shrink protected columns below word-min to absolute_min
        if excess > 0.01:
            for col_idx in range(min(protected_column_count, num_columns)):
                if excess <= 0:
                    break
                reducible = column_widths[col_idx] - absolute_min
                if reducible > 0:
                    take = min(excess, reducible)
                    column_widths[col_idx] -= take
                    excess -= take
        
        # Step 6g: Scale all proportionally (emergency)
        if excess > 0.01:
            scale = table_width / sum(column_widths)
            column_widths = [w * scale for w in column_widths]
            print("    ⚠️ WARNING: All columns scaled to fit - some data may wrap")
    
    elif current_sum < table_width:
        # Need to expand - give extra to columns that need it most
        extra = table_width - current_sum
        
        # First, give extra to protected columns if below ideal
        for col_idx in range(min(protected_column_count, num_columns)):
            if extra <= 0:
                break
            ideal = protected_col_ideal_widths.get(col_idx, column_widths[col_idx])
            if column_widths[col_idx] < ideal:
                can_add = ideal - column_widths[col_idx]
                add_amount = min(extra, can_add)
                column_widths[col_idx] += add_amount
                extra -= add_amount
        
        # Then distribute remaining to cols 3+ based on wrap scores
        if extra > 0.01 and wrappable_indices:
            expand_wrap_scores: Dict[int, float] = {}
            for col_idx in wrappable_indices:
                expand_wrap_scores[col_idx] = calc_wrap_score(col_idx, column_widths[col_idx])
            
            total_wrap_score = sum(expand_wrap_scores.values())
            
            if total_wrap_score > 0:
                for col_idx in wrappable_indices:
                    proportion = expand_wrap_scores[col_idx] / total_wrap_score
                    column_widths[col_idx] += extra * proportion
            else:
                # Equal distribution if no wrapping
                equal_share = extra / len(wrappable_indices)
                for col_idx in wrappable_indices:
                    column_widths[col_idx] += equal_share
        elif extra > 0.01:
            # No cols 3+ - distribute equally to all
            equal_share = extra / num_columns
            for col_idx in range(num_columns):
                column_widths[col_idx] += equal_share
    
    # Final normalization to exactly match table_width
    final_sum = sum(column_widths)
    if abs(final_sum - table_width) > 0.001:
        scale = table_width / final_sum
        if scale < 1.0:
            shrink_needed = final_sum - table_width
            
            # 1. Try cols 3+ first
            if wrappable_indices and shrink_needed > 0:
                wrappable_total = sum(column_widths[i] for i in wrappable_indices)
                wrappable_min_total = absolute_min * len(wrappable_indices)
                shrink_available = wrappable_total - wrappable_min_total
                
                if shrink_available >= shrink_needed:
                    shrink_scale = (wrappable_total - shrink_needed) / wrappable_total
                    for i in wrappable_indices:
                        column_widths[i] = max(absolute_min, column_widths[i] * shrink_scale)
                    shrink_needed = 0
                else:
                    for i in wrappable_indices:
                        column_widths[i] = absolute_min
                    shrink_needed -= shrink_available
            
            # 2. Then col 2 to data-only (headers can wrap)
            if shrink_needed > 0 and num_columns > 1:
                col_1_data_only = protected_col_data_only_widths.get(1, absolute_min)
                reducible = column_widths[1] - col_1_data_only
                if reducible > 0:
                    take = min(shrink_needed, reducible)
                    column_widths[1] -= take
                    shrink_needed -= take
            
            # 3. Then col 1 to data-only (headers can wrap)
            if shrink_needed > 0 and num_columns > 0:
                col_0_data_only = protected_col_data_only_widths.get(0, absolute_min)
                reducible = column_widths[0] - col_0_data_only
                if reducible > 0:
                    take = min(shrink_needed, reducible)
                    column_widths[0] -= take
                    shrink_needed -= take
            
            # 4. Then col 2 to word-min
            if shrink_needed > 0 and num_columns > 1:
                col_1_word_min = protected_col_min_widths.get(1, absolute_min)
                reducible = column_widths[1] - col_1_word_min
                if reducible > 0:
                    take = min(shrink_needed, reducible)
                    column_widths[1] -= take
                    shrink_needed -= take
            
            # 5. Then col 1 to word-min (LAST RESORT)
            if shrink_needed > 0 and num_columns > 0:
                col_0_word_min = protected_col_min_widths.get(0, absolute_min)
                reducible = column_widths[0] - col_0_word_min
                if reducible > 0:
                    take = min(shrink_needed, reducible)
                    column_widths[0] -= take
                    shrink_needed -= take
            
            # 6. Emergency: scale all
            if shrink_needed > 0.001:
                column_widths = [w * scale for w in column_widths]
        else:
            # Expanding: scale all columns
            column_widths = [w * scale for w in column_widths]
    
    # Final debug output
    col_details = []
    for i in range(num_columns):
        col_type = "P" if i < protected_column_count else "W"  # P=protected, W=wrappable
        col_details.append(f"{columns[i][:12]}[{col_type}]={column_widths[i]:.2f}")
    
    print(f"    📊 FINAL column widths: {[f'{w:.2f}' for w in column_widths]}, sum={sum(column_widths):.3f}")
    print(f"    📊 Details: {col_details}")

    return column_widths


def calculate_table_content_height(
    data: List[Dict[str, Any]],
    table_width: float,
    element_dims: Any,
    has_header: bool = True,
    max_columns: Optional[int] = None,
    has_source: bool = False,
) -> Tuple[float, List[float], List[float]]:
    """
    Calculate table height based on actual content and text wrapping.

    THIS IS THE SINGLE SOURCE OF TRUTH FOR ALL TABLE HEIGHT CALCULATIONS.
    Both assignment phase (slide_number_assigner) and rendering phase
    (TableBlock.calculate_content_based_height) must use this function
    to ensure consistent height calculations.

    This method calculates the height required for each row based on cell content,
    column widths, and font metrics, accounting for text wrapping.

    The first column is expanded to fit its content without wrapping, while
    remaining columns share the leftover space equally.

    Args:
        data: Table data (list of dictionaries)
        table_width: Available width for the table in inches
        element_dims: ElementDimensions config object
        has_header: Whether table has header row
        max_columns: Maximum columns to use (template limit). If None, defaults to 11.
        has_source: Whether table has a source row (added as a row inside the table)

    Returns:
        Tuple of (total_table_height, list_of_row_heights, list_of_column_widths)
        - total_table_height: Total height of table content including source row (no labels)
        - list_of_row_heights: List of heights for each row [header, row1, row2, ..., source_row?]
        - list_of_column_widths: List of column widths in inches [col1_width, col2_width, ...]
    """
    # Handle no data case
    if not data or len(data) == 0:
        rows_to_use = 5
        row_heights = [element_dims.table_min_row_height] * rows_to_use
        return (sum(row_heights), row_heights, [])

    # --- STEP 1: Determine columns ---
    # Default to 12 columns (matches typical table templates) when not specified
    # This ensures consistent height calculation between assignment and orchestrator
    default_max_columns = getattr(element_dims, "table_default_max_columns", 12)
    template_column_limit = max_columns if max_columns is not None else default_max_columns
    all_columns = list(data[0].keys()) if data else []
    columns = all_columns[:template_column_limit]
    num_columns = len(columns)

    if num_columns == 0:
        row_heights = [element_dims.table_min_row_height] * len(data)
        return (sum(row_heights), row_heights, [])

    # --- STEP 2: Calculate variable column widths ---
    # First column expands to fit content, remaining columns share leftover space
    column_widths = calculate_column_widths(
        data=data,
        table_width=table_width,
        element_dims=element_dims,
        columns=columns,
        has_header=has_header,
    )

    # --- STEP 3: Calculate per-column chars_per_line ---
    # Cell horizontal margins (convert from points to inches)
    # NOTE: Set to 0 for chars_per_line calculation - the margin is physical padding,
    # but doesn't affect how many characters fit per line in PowerPoint's text wrapping
    cell_h_margin_inches = 0

    # Character width for row HEIGHT calculation
    # CALIBRATED 2024-12-22: Use dynamic ratio based on column width
    # - Narrow columns (<0.55"): use higher ratio (0.42) → more conservative wrapping
    # - Wide columns (>=0.55"): use base ratio (0.35) → less wrapping
    # This matches observed PowerPoint behavior where narrow columns wrap 10-char values
    font_size_pt = element_dims.table_font_size
    base_char_width_ratio = element_dims.table_char_width_ratio_for_row_height  # 0.35
    narrow_column_threshold = getattr(
        element_dims, "table_narrow_column_threshold_inches", 0.55
    )
    narrow_column_ratio = getattr(
        element_dims, "table_narrow_column_char_width_ratio_for_row_height", 0.37
    )
    header_narrow_column_ratio = getattr(
        element_dims,
        "table_header_narrow_column_char_width_ratio_for_row_height",
        narrow_column_ratio,
    )
    text_column_max_width_inches = float(
        getattr(element_dims, "table_text_column_max_width_inches", 1.05)
    )
    text_alpha_ratio = float(
        getattr(
            element_dims, "table_text_alpha_column_char_width_ratio_for_row_height", 0.45
        )
    )
    text_mixed_ratio = float(
        getattr(
            element_dims, "table_text_mixed_column_char_width_ratio_for_row_height", 0.55
        )
    )
    text_min_alpha_ratio = float(
        getattr(element_dims, "table_text_column_min_alpha_ratio", 0.20)
    )
    text_min_space_ratio = float(
        getattr(element_dims, "table_text_column_min_space_ratio", 0.05)
    )
    text_min_digit_ratio_for_mixed = float(
        getattr(element_dims, "table_text_column_min_digit_ratio_for_mixed", 0.15)
    )

    _alpha_re = re.compile(r"[A-Za-z]")
    _space_re = re.compile(r"\s")
    _digit_re = re.compile(r"\d")

    def _get_text_column_ratio(col_name: str) -> float | None:
        """
        Heuristic classification (config-driven thresholds, no hardcoded column names).

        We sample up to N values in the column and (if text-heavy) return a calibrated
        char-width ratio:
        - alpha-heavy columns (names): text_alpha_ratio
        - mixed digit+word columns (addresses): text_mixed_ratio
        """
        sample_n = min(10, len(data))
        if sample_n <= 0:
            return None

        alpha = 0
        spaces = 0
        digits = 0
        total = 0

        for row in data[:sample_n]:
            v = str(row.get(col_name, "") or "")
            if not v:
                continue
            total += len(v)
            alpha += len(_alpha_re.findall(v))
            spaces += len(_space_re.findall(v))
            digits += len(_digit_re.findall(v))

        if total <= 0:
            return None

        alpha_ratio = alpha / total
        space_ratio = spaces / total
        digit_ratio = digits / total

        is_text_heavy = alpha_ratio >= text_min_alpha_ratio and space_ratio >= text_min_space_ratio
        if not is_text_heavy:
            return None

        # Address-like (digits + words) tends to wrap more aggressively in PowerPoint
        return text_mixed_ratio if digit_ratio >= text_min_digit_ratio_for_mixed else text_alpha_ratio

    def _chars_per_line_for_col(col_width: float, *, is_header: bool) -> int:
        usable_width = col_width - cell_h_margin_inches
        # Use higher ratio for narrow columns (causes more wrapping).
        # Headers wrap more aggressively in PowerPoint, so they use a separate ratio.
        if col_width < narrow_column_threshold:
            char_width_ratio = (
                header_narrow_column_ratio if is_header else narrow_column_ratio
            )
        elif is_header:
            # Headers use same base ratio as data for consistency
            # The 0.65 was too conservative - causing over-tall headers with extra vertical space
            char_width_ratio = base_char_width_ratio  # 0.50
        elif col_width <= text_column_max_width_inches:
            # For narrow-ish columns containing multi-word phrases, PowerPoint tends to wrap
            # more aggressively (word boundaries), effectively allowing fewer chars per line.
            # Apply a more conservative ratio for text-heavy columns only.
            # NOTE: We decide text-heaviness per-column below and override chars-per-line.
            char_width_ratio = base_char_width_ratio
        else:
            char_width_ratio = base_char_width_ratio
        char_width_inches = (font_size_pt * char_width_ratio) / 72.0
        return max(1, int(usable_width / char_width_inches))

    # Calculate chars_per_line for each column based on its width.
    # If a column is text-heavy and narrow-ish, use a more conservative ratio to mimic
    # PowerPoint’s word-wrapping behavior for multi-word phrases.
    chars_per_line_per_column_data = []
    for col_idx, col_width in enumerate(column_widths):
        base_cpl = _chars_per_line_for_col(col_width, is_header=False)
        if col_idx < len(columns):
            col_name = columns[col_idx]
            text_ratio_for_col = (
                _get_text_column_ratio(col_name)
                if col_width <= text_column_max_width_inches
                else None
            )
            if text_ratio_for_col is not None:
                usable_width = col_width - cell_h_margin_inches
                char_width_inches = (font_size_pt * text_ratio_for_col) / 72.0
                base_cpl = max(1, int(usable_width / char_width_inches))
        chars_per_line_per_column_data.append(base_cpl)

    chars_per_line_per_column_header = [
        _chars_per_line_for_col(col_width, is_header=True) for col_width in column_widths
    ]

    # --- STEP 4: Define cell height calculation ---
    # PowerPoint uses WORD wrapping, not character wrapping
    # Line height = font size × line spacing multiplier (single spacing is ~1.0, PowerPoint uses ~1.15-1.2)
    line_spacing_multiplier = element_dims.table_line_spacing_multiplier
    line_height_inches = (font_size_pt / 72.0) * line_spacing_multiplier

    # PowerPoint row height formula:
    #   row_height = max(min_row_height, num_lines × line_height)
    #
    # CALIBRATED 2026-01-28: The min_row_height (0.265") already includes cell padding
    # and overhead based on actual measurements. Adding cell_v_padding caused over-estimation.
    # Data rows: actual=0.27", with padding=0.293" (over-estimate)
    cell_v_padding_inches = 0.0  # Already included in min_row_height
    row_overhead_inches = 0.0  # No additional per-row overhead

    max_wrapped_lines = int(getattr(element_dims, "table_max_wrapped_lines", 5))

    def count_word_wrapped_lines(text: str, max_chars: int) -> int:
        """Count lines needed using word wrapping (like PowerPoint does)."""
        if not text or max_chars <= 0:
            return 1

        words = text.split()
        if not words:
            return 1

        lines = 1
        current_line_len = 0

        for word in words:
            word_len = len(word)

            if current_line_len == 0:
                # First word on line
                if word_len > max_chars:
                    # Word is longer than line - will wrap mid-word
                    lines += (word_len - 1) // max_chars
                current_line_len = word_len
            elif current_line_len + 1 + word_len <= max_chars:
                # Word fits on current line (with space)
                current_line_len += 1 + word_len
            else:
                # Word doesn't fit, start new line
                lines += 1
                if word_len > max_chars:
                    # Word is longer than line - will wrap mid-word
                    lines += (word_len - 1) // max_chars
                current_line_len = word_len

        return lines

    def calculate_cell_height(text: str, col_idx: int, *, is_header: bool) -> float:
        """Calculate height needed for a cell based on text content and column width."""
        chars_per_line_list = (
            chars_per_line_per_column_header
            if is_header
            else chars_per_line_per_column_data
        )
        chars_per_line = chars_per_line_list[col_idx] if col_idx < len(chars_per_line_list) else 10
        lines_needed = count_word_wrapped_lines(text, chars_per_line)
        # Cap at reasonable max
        lines_needed = min(lines_needed, max_wrapped_lines)

        # Row height = (lines × line_height) + vertical padding + overhead
        content_height: float = float(
            (lines_needed * line_height_inches)
            + cell_v_padding_inches
            + row_overhead_inches
        )
        # Enforce minimum row height (which already includes cell padding)
        min_row_height: float = float(element_dims.table_min_row_height)
        return max(content_height, min_row_height)

    # --- STEP 5: Calculate height for each row ---
    row_heights = []
    min_cell_height = element_dims.table_min_row_height  # Use configured minimum

    # Header row (if present)
    # Headers get extra padding for bold text/styling
    if has_header:
        max_header_height = min_cell_height
        for col_idx, col_name in enumerate(columns):
            cell_height = calculate_cell_height(str(col_name), col_idx, is_header=True)
            max_header_height = max(max_header_height, cell_height)
        
        # CALIBRATED 2026-01-28: Use adaptive header padding based on calculated height
        # - Headers at minimum height (no wrapping) don't need extra padding
        # - Short wrapping headers (min < height < 0.40") tend to be UNDERESTIMATED in PPT
        #   due to cell padding and bold text rendering overhead. Use padding to compensate.
        # - Tall headers (>= 0.40") are already accurate - PPT doesn't add extra padding
        #   for multi-line headers beyond what's in the line height.
        # Calibration data:
        #   - Figure 8 header: raw=0.32", actual=0.42", delta=0.10"
        header_height_threshold = 0.40  # Threshold for adaptive padding
        short_header_extra_padding = 0.10  # Calibrated: 0.42" - 0.32" = 0.10"
        
        # Only apply adaptive padding if header has SOME wrapping (> min) but is still short (< 0.40")
        # Headers at min_cell_height (no wrapping) should stay at minimum
        header_has_wrapping = max_header_height > min_cell_height + 0.01  # Small tolerance
        if header_has_wrapping and max_header_height < header_height_threshold:
            max_header_height += short_header_extra_padding
        # No extra padding for:
        # - Headers at minimum (no wrapping)
        # - Tall headers (>= 0.40") - line height already accounts for spacing
        
        row_heights.append(max_header_height)

    # Data rows
    ROW_DEBUG = False  # Set True for detailed row debugging
    for row_idx, row_data in enumerate(data):
        max_cell_height = min_cell_height
        max_cell_info = ("", 0, 0)  # (col_name, text_len, cpl)
        for col_idx, col_name in enumerate(columns):
            cell_text = str(row_data.get(col_name, ""))
            cell_height = calculate_cell_height(cell_text, col_idx, is_header=False)
            if cell_height > max_cell_height:
                max_cell_height = cell_height
                cpl = chars_per_line_per_column_data[col_idx] if col_idx < len(chars_per_line_per_column_data) else 0
                max_cell_info = (col_name, len(cell_text), cpl)
        if ROW_DEBUG:
            if max_cell_height > min_cell_height:
                print(f"      Row {row_idx+1}: height={max_cell_height:.2f}\" driven by {max_cell_info[0]} ({max_cell_info[1]} chars, CPL={max_cell_info[2]})")
            else:
                # Show ALL cells with their CPL to debug why none wrapped
                cell_details = []
                for col_idx, col_name in enumerate(columns):
                    cell_text = str(row_data.get(col_name, ""))
                    cpl = chars_per_line_per_column_data[col_idx] if col_idx < len(chars_per_line_per_column_data) else 0
                    if len(cell_text) > 0:
                        cell_details.append(f"{col_name[:10]}={len(cell_text)}/{cpl}")
                print(f"      Row {row_idx+1}: height={max_cell_height:.2f}\" (no wrap) cells: {', '.join(cell_details[:5])}")
        row_heights.append(max_cell_height)

    # --- STEP 6: Add source row height if present ---
    # Source row is added INSIDE the table as an actual row.
    # IMPORTANT: Use config-driven height that matches PowerPoint's reported row height.
    # Note: Source row height is already calibrated from actual measurements,
    # so we do NOT apply the safety margin to it.
    if has_source:
        source_row_height = element_dims.table_source_row_height
        row_heights.append(source_row_height)

    # --- STEP 7: Sum all row heights and add border/padding overhead ---
    # Border/row-gap overhead is config-driven. For our current templates, these are 0.0.
    row_heights_sum = sum(row_heights)
    num_rows = len(row_heights)

    # Border and padding overhead - PowerPoint adds visual space beyond row heights
    # Use config values for consistency across all calculations

    # Base border overhead (top + bottom borders) - from config
    border_overhead = element_dims.table_border_overhead

    # Cell padding between rows - from config for consistency
    cell_padding_per_gap = element_dims.table_row_gap_padding
    cell_padding_between_rows = cell_padding_per_gap * max(0, num_rows - 1)

    total_height = row_heights_sum + border_overhead + cell_padding_between_rows

    # --- DETAILED CALIBRATION LOGGING ---
    # This output helps calibrate the height estimation formula
    if CALIBRATION_DEBUG:
        print("\n" + "=" * 70)
        print("📏 TABLE HEIGHT CALIBRATION BREAKDOWN")
        print("=" * 70)
        print(f'Table width: {table_width:.3f}"')
        print(f"Font size: {font_size_pt}pt")
        print(f"Line spacing multiplier: {line_spacing_multiplier}")
        print(
            f'Line height: {line_height_inches:.4f}" (font_size/72 × {line_spacing_multiplier})'
        )
        print("Row formula: max(min_row_height, lines × line_height)")
        print(f'Min row height: {element_dims.table_min_row_height:.3f}"')
        print(f"Columns: {num_columns} (limited to {template_column_limit})")
        print("-" * 70)
        print("PER-ROW BREAKDOWN:")
        print("-" * 70)

        row_idx = 0
        # Header row
        if has_header:
            header_text = ", ".join(str(c)[:15] for c in columns[:3])
            if len(columns) > 3:
                header_text += f"... (+{len(columns) - 3} more)"
            print(
                f"  Row {row_idx:2d} (Header): height={row_heights[row_idx]:.4f}\" | '{header_text}'"
            )
            row_idx += 1

        # Data rows
        for i, row_data in enumerate(data):
            if row_idx < len(row_heights):
                # Get first column text for reference
                first_col_text = str(row_data.get(columns[0], ""))[:20]
                longest_cell_len = 0
                for col_name in columns:
                    cell_text = str(row_data.get(col_name, ""))
                    if len(cell_text) > longest_cell_len:
                        longest_cell_len = len(cell_text)

                print(
                    f"  Row {row_idx:2d} (Data {i + 1:2d}): height={row_heights[row_idx]:.4f}\" | first='{first_col_text}' | longest={longest_cell_len} chars"
                )
                row_idx += 1

        # Source row
        if has_source and row_idx < len(row_heights):
            print(
                f"  Row {row_idx:2d} (Source): height={row_heights[row_idx]:.4f}\" | 'Source: ...'"
            )

        print("-" * 70)
        print("HEIGHT CALCULATION:")
        print("-" * 70)
        print(f'  Sum of row heights:          {row_heights_sum:.4f}"')
        print(f'  Border overhead:           + {border_overhead:.4f}"')
        print(
            f'  Row gaps ({num_rows - 1} gaps × {cell_padding_per_gap:.3f}"):  + {cell_padding_between_rows:.4f}"'
        )
        print("-" * 70)
        print(f'  ESTIMATED TOTAL HEIGHT:      {total_height:.4f}"')
        print("=" * 70)
        print("Compare this with actual PowerPoint height (Size and Position)")
        print("=" * 70 + "\n")

    return (total_height, row_heights, column_widths)


def calculate_chart_content_height(
    chart_data: List[Dict[str, Any]],
    chart_width: float,
    element_dims: Any,
    chart_type: Optional[str] = None,
) -> float:
    """
    Calculate chart height based on content (number of series, legend size, etc.).

    Args:
        chart_data: Chart data (list of dictionaries)
        chart_width: Available width for the chart in inches
        element_dims: ElementDimensions config object
        chart_type: Type of chart (e.g., 'column', 'pie', 'line')

    Returns:
        Total chart content height in inches (chart + legend, no labels/source)
    """
    # Estimate aspect ratio height
    aspect_ratio = 1.6  # Default aspect ratio for charts
    base_height = chart_width / aspect_ratio

    # Estimate legend height based on chart data
    series_count = 1  # Default
    if chart_data and len(chart_data) > 0:
        if isinstance(chart_data[0], dict):
            columns = list(chart_data[0].keys())
            series_count = len(columns) - 1 if len(columns) > 1 else 1

        # Legend height estimation
        # Each series takes approximately 0.15 inches in legend
        # Plus 0.1 inches for legend padding/border
        legend_height = series_count * 0.15 + 0.1

        # Cap legend height at reasonable max
        legend_height = min(legend_height, 1.0)
    else:
        # Default legend height
        legend_height = 0.3

    # Special handling for chart types
    if chart_type and chart_type.lower() in ("pie", "donut"):
        # Pie charts are more square-ish and have legend to the side
        # They don't need as much vertical space for legend
        total_height = base_height
    else:
        # Most chart types have legend at bottom
        total_height = base_height + legend_height

    # Ensure minimum chart height
    min_chart_height = (
        element_dims.chart_min_height
        if hasattr(element_dims, "chart_min_height")
        else 2.0
    )
    total_height = max(total_height, min_chart_height)

    return total_height


def calculate_total_element_height(
    content_height: float,
    element: Dict[str, Any],
    is_first_in_section: bool,
    section_style: Optional[Dict[str, Any]],
    element_dims: Any,
) -> float:
    """
    Calculate total element height including all components:
    - Section title (if first element and section.style.show_title is True)
    - Figure/table label
    - Content (table or chart)
    - Source label

    Args:
        content_height: Height of the content itself (table or chart)
        element: Element dictionary with config
        is_first_in_section: Whether this is the first element in the section
        section_style: Section style dictionary (contains show_title flag)
        element_dims: ElementDimensions config object

    Returns:
        Total element height in inches including all components
    """
    total_height = 0.0

    # Section title (first element only)
    # Default behavior: show titles unless explicitly disabled in section_style.
    show_title = True if section_style is None else section_style.get("show_title", True)
    if is_first_in_section and show_title:
        total_height += element_dims.get_section_title_total_height()

    # Figure/table label - ALWAYS reserve space for tables and charts
    # Labels are added during rendering even if not explicitly in config
    element_type = element.get("element_type", "")
    config = element.get("config", {})

    # Check if label is explicitly set OR if this is a table/chart (which always get labels)
    has_label = any(
        [
            config.get("figure_label"),
            config.get("figure_name"),
            config.get("table_label"),
            config.get("label"),
            element_type in ["table", "chart"],  # Tables and charts ALWAYS get labels
        ]
    )
    if has_label:
        # Use table-specific gap for tables (larger than chart gap to prevent overlapping)
        if element_type == "table":
            total_height += element_dims.get_table_label_total_height()
        else:
            total_height += element_dims.get_figure_label_total_height()

    # Content (table/chart)
    total_height += content_height

    # Source label space
    # For tables: source is now a row INSIDE the table, already included in content_height
    #             from calculate_table_content_height() when has_source=True
    # For charts: source is still external, so add source_gap + source_label_height
    has_source = any(
        [
            config.get("figure_source"),
            config.get("table_source"),
            config.get("source"),
            element_type in ["table", "chart"],  # Tables and charts ALWAYS get sources
        ]
    )
    if has_source:
        if element_type == "table":
            # Table source row height is ALREADY included in content_height
            # (added as a row in calculate_table_content_height when has_source=True)
            # Do NOT add it again here to avoid double-counting
            pass
        else:
            # Chart/other source is external
            total_height += element_dims.source_gap + element_dims.source_label_height

    return total_height


def calculate_max_rows_for_height(
    data: List[Dict[str, Any]],
    table_width: float,
    max_height: float,
    element_dims: Any,
    has_header: bool = True,
    max_columns: Optional[int] = None,
    has_source: bool = False,
) -> int:
    """
    Calculate maximum number of data rows that can fit in a given height.

    Uses content-based height calculation to progressively add rows until
    max_height is exceeded. Uses same overhead values as calculate_table_content_height.

    Args:
        data: Table data (list of dictionaries)
        table_width: Available width for the table in inches
        max_height: Maximum height available in inches
        element_dims: ElementDimensions config object
        has_header: Whether table has header row
        max_columns: Maximum columns to use (template limit)
        has_source: Whether table has a source row

    Returns:
        Maximum number of data rows that fit (excluding header)
    """
    if not data:
        return 0

    # Get row heights using the shared calculation method
    # Include source row in calculation since it takes up space
    _, row_heights, _ = calculate_table_content_height(
        data=data,
        table_width=table_width,
        element_dims=element_dims,
        has_header=has_header,
        max_columns=max_columns,
        has_source=has_source,
    )

    if not row_heights:
        return 0

    # Use same overhead values as calculate_table_content_height for consistency
    border_overhead = element_dims.table_border_overhead
    row_gap_padding = element_dims.table_row_gap_padding

    # Available height after subtracting border overhead
    available_height = max_height - border_overhead

    # Header row (if present) - subtract height + gap after header
    if has_header and len(row_heights) > 0:
        header_height = row_heights[0]
        available_height -= header_height
        available_height -= row_gap_padding  # Gap after header
        data_row_start = 1
    else:
        data_row_start = 0

    if available_height <= 0:
        return 0

    # Add data rows one by one until we exceed available height
    # Account for row gap padding between rows
    rows_that_fit = 0
    for idx in range(data_row_start, len(row_heights)):
        row_height = row_heights[idx]

        # Add gap before this row (except first data row after header which already has gap accounted)
        gap_needed = row_gap_padding if rows_that_fit > 0 else 0
        total_needed = row_height + gap_needed

        if available_height >= total_needed:
            rows_that_fit += 1
            available_height -= total_needed
        else:
            break

    return max(1, rows_that_fit)  # Always keep at least 1 row

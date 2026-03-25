#!/usr/bin/env python3
from __future__ import annotations
"""
Slide Number Assigner - Intelligent slide number assignment for PPT generation

This module assigns slide numbers to elements based on:
- Section display_order (primary grouping)
- Element display_order within sections
- Template-specific layout constraints (via template_config.py)
- 2x2 grid capacity (4 elements per slide)
- Element size estimation and overflow handling
- First slide special handling (Base with KPIs template)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple, Optional, List, Set, Callable
import copy
from app.utils.logger import logger

from app.ppt_engine.ppt_helpers_utils.services.template_config import (
    SlideLayoutConfig,
    SlideConstraints,
    get_slide_layout_config,
    get_allowed_layout_types,
    get_element_dimensions,
    get_layout_preference_config,
    LayoutPreferenceConfig,
    LayoutPreferenceRule,
    determine_layout_type_from_criteria,
)

# ============================================================================
# LAYOUT METRICS
# ============================================================================

DEFAULT_PROPERTY_SUB_TYPE = "figures"
DEFAULT_GRID_ROWS = 2
DEFAULT_GRID_COLS = 2

_BASE_LAYOUT_CONFIG = get_slide_layout_config(DEFAULT_PROPERTY_SUB_TYPE)
_BASE_CONSTRAINTS = _BASE_LAYOUT_CONFIG.get_constraints(is_first_slide=False)
_BASE_QUADRANT_WIDTH = (
    (_BASE_CONSTRAINTS.content_width - _BASE_CONSTRAINTS.gutter_horizontal)
    / DEFAULT_GRID_COLS
)
_BASE_QUADRANT_HEIGHT = (
    (_BASE_CONSTRAINTS.content_height - _BASE_CONSTRAINTS.gutter_vertical)
    / DEFAULT_GRID_ROWS
)


@dataclass(frozen=True)
class SlideLayoutMetrics:
    """Concrete layout measurements derived from template_config."""

    property_sub_type: Optional[str]
    constraints: SlideConstraints
    layout_config: SlideLayoutConfig  # Unified layout config
    content_width: float
    content_height: float
    quadrant_width: float
    quadrant_height: float
    first_slide_capacity: int
    regular_slide_capacity: int


@dataclass
class SlideState:
    """
    Encapsulates current slide assignment state (Single Responsibility Principle).
    
    This class tracks all state needed during slide number assignment,
    making the assignment logic cleaner and more maintainable.
    """
    slide_number: int = 1
    elements_count: int = 0
    is_first_slide: bool = True
    cumulative_height: float = 0.0
    layout: Optional[str] = None  # Track current slide's layout type
    
    def reset_for_new_slide(self, new_slide_number: int) -> None:
        """Reset state when moving to a new slide."""
        self.slide_number = new_slide_number
        self.elements_count = 0
        self.is_first_slide = False
        self.cumulative_height = 0.0
        self.layout = None
    
    def can_accept_layout(self, new_layout: str) -> bool:
        """Check if this slide can accept elements with the given layout."""
        if self.layout is None:
            return True  # No layout set yet, can accept any
        return self.layout == new_layout
    
    def set_layout(self, layout_type: str) -> None:
        """Set the layout for this slide (only if not already set)."""
        if self.layout is None:
            self.layout = layout_type


def _calculate_quadrant_dimension(
    total_available: float, gutter: float, slots: int
) -> float:
    """Return the usable dimension per slot, accounting for gutters."""
    if slots <= 0:
        return total_available
    total_gutter = gutter * max(0, slots - 1)
    usable = max(total_available - total_gutter, 0.0)
    return usable / slots if slots else usable


def _build_layout_metrics(json_data: Dict[str, Any]) -> SlideLayoutMetrics:
    """Resolve slide layout metrics for the provided JSON payload."""
    report_meta = json_data.get("report") or {}
    sub_type_raw = report_meta.get("property_sub_type") or report_meta.get("report_type")
    property_sub_type = (sub_type_raw or DEFAULT_PROPERTY_SUB_TYPE).strip().lower()

    layout_config = get_slide_layout_config(property_sub_type)
    constraints = layout_config.get_constraints(is_first_slide=False)
    first_slide_constraints = layout_config.get_constraints(is_first_slide=True)

    # Grid only applies if property_sub_type is figures or submarket
    uses_grid = property_sub_type in ("figures", "submarket")
    
    if uses_grid:
        quadrant_width = _calculate_quadrant_dimension(
            constraints.content_width, constraints.gutter_horizontal, DEFAULT_GRID_COLS
        )
        quadrant_height = _calculate_quadrant_dimension(
            constraints.content_height, constraints.gutter_vertical, DEFAULT_GRID_ROWS
        )
    else:
        # For non-grid types, use full content dimensions
        quadrant_width = constraints.content_width
        quadrant_height = constraints.content_height

    # Determine slide capacities based on unified config
    if layout_config.uses_dynamic_capacity:
        # Dynamic capacity will be calculated later in _update_dynamic_capacities
        # Use fallback values for now
        first_slide_capacity = layout_config.first_slide_capacity or 1
        regular_slide_capacity = layout_config.regular_slide_capacity or 1
    else:
        # Use fixed capacities from config
        if layout_config.first_slide_capacity is not None:
            first_slide_capacity = layout_config.first_slide_capacity
        elif layout_config.first_slide_max_elements:
            first_slide_capacity = layout_config.first_slide_max_elements
        elif layout_config.first_slide_rows and layout_config.first_slide_cols:
            first_slide_capacity = layout_config.first_slide_rows * layout_config.first_slide_cols
        else:
            first_slide_capacity = DEFAULT_GRID_ROWS * DEFAULT_GRID_COLS if uses_grid else 1
        
        if layout_config.regular_slide_capacity is not None:
            regular_slide_capacity = layout_config.regular_slide_capacity
        else:
            regular_slide_capacity = DEFAULT_GRID_ROWS * DEFAULT_GRID_COLS if uses_grid else 1

    return SlideLayoutMetrics(
        property_sub_type=property_sub_type,
        constraints=constraints,
        layout_config=layout_config,
        content_width=constraints.content_width,
        content_height=constraints.content_height,
        quadrant_width=quadrant_width,
        quadrant_height=quadrant_height,
        first_slide_capacity=first_slide_capacity,
        regular_slide_capacity=regular_slide_capacity,
    )


# ============================================================================
# DYNAMIC CAPACITY CALCULATION FUNCTIONS
# ============================================================================

def _calculate_dynamic_slide_capacity(
    elements: list[Dict[str, Any]], 
    layout: SlideLayoutMetrics, 
    is_first_slide: bool = False
) -> int:
    """
    Calculate dynamic slide capacity based on element heights for submarket and snapshot.
    Uses layout-aware height calculation for accuracy.
    
    Args:
        elements: List of elements to fit on the slide
        layout: SlideLayoutMetrics with property_sub_type info
        is_first_slide: True if calculating for first slide
        
    Returns:
        Number of elements that can fit on the slide
    """
    if not elements:
        return 1
    
    # For first slide, calculate available height accounting for KPI section
    if is_first_slide and layout.layout_config.first_slide_start_top is not None:
        # Calculate actual available height for first slide (below KPIs)
        first_slide_margin_bottom = (
            layout.layout_config.first_slide_margin_bottom or 
            layout.layout_config.base_constraints.margin_bottom
        )
        available_height = (
            layout.constraints.slide_height - 
            layout.layout_config.first_slide_start_top - 
            first_slide_margin_bottom
        )
    else:
        # Regular slide uses standard content_height
        available_height = layout.content_height
    
    gutter_vertical = layout.constraints.gutter_vertical
    
    # Get element dimensions
    element_dims = get_element_dimensions()
    
    # Calculate cumulative height for each element
    cumulative_height = 0.0
    capacity = 0
    
    # For submarket and snapshot, elements typically use full_width layout
    layout_type = "full_width"
    
    # Identify first element by display_order (lowest value)
    first_element = None
    if elements:
        elements_with_order = [e for e in elements if e.get("display_order") is not None]
        if elements_with_order:
            first_element = min(elements_with_order, key=lambda e: e.get("display_order", 0))
        else:
            # Fallback to first element in list
            first_element = elements[0]
    
    for element in elements:
        # Check if this is the first element of the section
        is_first_element_of_section = (element is first_element)
        
        # Use layout-aware height calculation
        element_height = _calculate_element_height_for_layout(
            element, layout_type, layout, is_first_slide,
            is_first_element_of_section=is_first_element_of_section
        )
        
        # Check if adding this element would exceed available height
        height_needed = element_height
        if capacity > 0:  # Add gutter for subsequent elements
            height_needed += gutter_vertical
        
        # Check if element fits
        # For full_width layouts with overflow enabled, allow elements to exceed available height
        # (they'll be split during rendering, but we count them for capacity)
        element_dims = get_element_dimensions()
        allow_overflow = element_dims.allow_full_width_overflow and layout_type == "full_width"
        
        if cumulative_height + height_needed <= available_height:
            # Element fits within available height
            cumulative_height += height_needed
            capacity += 1
        elif allow_overflow and capacity == 0:
            # First element can overflow (will be split during rendering)
            capacity += 1
            break  # Don't add more elements after overflow
        else:
            # Element doesn't fit and overflow not allowed (or not first element)
            break  # Can't fit more elements
    
    return max(1, capacity)  # Ensure at least 1 element per slide


def _update_dynamic_capacities(
    layout_metrics: SlideLayoutMetrics, 
    sections: list[Dict[str, Any]]
) -> SlideLayoutMetrics:
    """
    Update slide capacities dynamically for submarket and snapshot property types.
    
    Args:
        layout_metrics: Current layout metrics
        sections: All sections with elements
        
    Returns:
        Updated SlideLayoutMetrics with dynamic capacities
    """
    property_sub_type = layout_metrics.property_sub_type
    
    if property_sub_type not in ("submarket", "snapshot"):
        return layout_metrics  # No dynamic calculation needed
    
    # Collect all elements from all sections
    all_elements = []
    first_slide_elements = []
    regular_slide_elements = []
    
    for section in sections:
        if not section.get("selected", True):
            continue
        elements = section.get("elements", [])
        selected_elements = [e for e in elements if e.get("selected", True)]
        all_elements.extend(selected_elements)
    
    if not all_elements:
        return layout_metrics
    
    # For snapshot, both first and regular capacities are dynamic
    if property_sub_type == "snapshot":
        # Calculate capacity based on typical element mix
        first_slide_capacity = _calculate_dynamic_slide_capacity(
            all_elements[:6],  # Sample first few elements
            layout_metrics, 
            is_first_slide=True
        )
        regular_slide_capacity = _calculate_dynamic_slide_capacity(
            all_elements,  # Use all elements for regular slide calculation
            layout_metrics, 
            is_first_slide=False
        )
    else:  # submarket
        # First slide capacity is fixed at 6, only regular capacity is dynamic
        first_slide_capacity = 6
        regular_slide_capacity = _calculate_dynamic_slide_capacity(
            all_elements,
            layout_metrics, 
            is_first_slide=False
        )
    
    # Return updated metrics
    return SlideLayoutMetrics(
        property_sub_type=layout_metrics.property_sub_type,
        constraints=layout_metrics.constraints,
        layout_config=layout_metrics.layout_config,
        content_width=layout_metrics.content_width,
        content_height=layout_metrics.content_height,
        quadrant_width=layout_metrics.quadrant_width,
        quadrant_height=layout_metrics.quadrant_height,
        first_slide_capacity=first_slide_capacity,
        regular_slide_capacity=regular_slide_capacity,
    )


# ============================================================================
# MAIN ASSIGNMENT FUNCTION
# ============================================================================

def assign_slide_numbers(json_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assign slide numbers to all elements in the JSON data.
    
    Processes sections by display_order, then elements within each section.
    Assigns slide numbers based on 2x2 grid capacity with intelligent overflow.
    
    Args:
        json_data: Input JSON with 'report' and 'sections' keys
        
    Returns:
        Modified JSON with slide_number assigned to each element's config
    """
    # Deep copy to avoid modifying original
    data = copy.deepcopy(json_data)
    
    sections = data.get("sections", [])
    if not sections:
        return data
    
    # Sort sections by display_order
    sections.sort(key=lambda s: s.get("display_order", 0))
    
    layout = _build_layout_metrics(data)

    # Update dynamic capacities for submarket and snapshot types
    if layout.property_sub_type in ("submarket", "snapshot"):
        layout = _update_dynamic_capacities(layout, sections)
        print(f"📐 Updated dynamic capacities for '{layout.property_sub_type}': "
              f"first={layout.first_slide_capacity}, regular={layout.regular_slide_capacity}")

    # STEP 1: Normalize layout preferences for all sections BEFORE first pass
    # This ensures we know the layout type during slide assignment
    print(f"\n{'='*60}")
    print(f"🎯 LAYOUT PREFERENCE NORMALIZATION (BEFORE ASSIGNMENT)")
    print(f"{'='*60}\n")
    
    section_normalized_layouts: Dict[int, Optional[str]] = {}  # Map section index to normalized layout
    for section_idx, section in enumerate(sections):
        if not section.get("selected", True):
            continue
        
        layout_preference = section.get("layout_preference")
        if layout_preference:
            # Normalize for middle slides (we don't know total_slides yet, so we'll normalize for slide 2)
            # First/last slide normalization will happen in second pass
            normalized = _normalize_layout_preference(
                layout_preference=layout_preference,
                property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
                slide_number=2,  # Use slide 2 as proxy for middle slides
                total_slides=None,  # Unknown during first pass
            )
            section_normalized_layouts[section_idx] = normalized
            if normalized:
                print(f"   Section {section_idx + 1}: '{layout_preference}' → '{normalized}'")
            else:
                print(f"   Section {section_idx + 1}: '{layout_preference}' → None (will use criteria)")
        else:
            section_normalized_layouts[section_idx] = None
            print(f"   Section {section_idx + 1}: No preference (will use criteria)")

    print(f"\n{'='*60}")
    print(f"🎯 SLIDE NUMBER ASSIGNMENT")
    print(f"{'='*60}\n")
    print(
        f"Processing {len(sections)} sections using layout profile "
        f"'{layout.property_sub_type}'..."
    )
    
    # Track current slide number and elements on current slide
    current_slide = 1
    elements_on_current_slide = 0
    is_first_slide = True
    
    # Global height tracker for cumulative height across sections
    global_cumulative_height = 0.0
    
    # Track current slide layout (for ensuring layout consistency within slides)
    current_slide_layout: Optional[str] = None
    
    # First pass: assign slide numbers to all elements
    for section_idx, section in enumerate(sections):
        section_name = section.get("name", section.get("key", f"Section {section_idx + 1}"))
        
        # Skip unselected sections
        if not section.get("selected", True):
            print(f"⊘ Skipping unselected section: {section_name}")
            continue
        
        elements = section.get("elements", [])
        if not elements:
            print(f"⊘ Section '{section_name}' has no elements")
            continue
        
        print(f"\n📊 Section {section_idx + 1}: {section_name}")
        print(f"   Elements: {len(elements)}")
        print(f"   Starting at slide: {current_slide} (current capacity: {elements_on_current_slide})")
        
        # Get normalized layout preference for this section
        normalized_layout = section_normalized_layouts.get(section_idx)
        layout_preference = section.get("layout_preference")
        if layout_preference:
            print(f"   Layout Preference: {layout_preference} → {normalized_layout or 'criteria-based'}")
        
        # Assign slide numbers for this section's elements
        current_slide, elements_on_current_slide, is_first_slide, global_cumulative_height, current_slide_layout = _assign_section_elements(
            section=section,
            start_slide=current_slide,
            elements_on_current_slide=elements_on_current_slide,
            is_first_slide=is_first_slide,
            layout=layout,
            layout_preference=layout_preference,
            normalized_layout=normalized_layout,  # Pass normalized layout
            total_slides=None,  # Will be calculated after first pass
            global_cumulative_height=global_cumulative_height,
            current_slide_layout=current_slide_layout,  # Pass current slide layout for sharing compatibility
        )
        
        print(f"   After section: slide {current_slide}, capacity: {elements_on_current_slide}, layout: {current_slide_layout}")
    
    # Calculate total slides after first pass
    total_slides = current_slide if elements_on_current_slide == 0 else current_slide
    
    print(f"\n{'='*60}")
    print(f"✅ ASSIGNMENT COMPLETE")
    print(f"   Total slides: {total_slides}")
    print(f"{'='*60}\n")
    
    # Second pass: normalize layout preferences with total slides information
    # This ensures layout_preference is properly ignored for first/last slides
    current_slide = 1
    elements_on_current_slide = 0
    is_first_slide = True
    
    for section_idx, section in enumerate(sections):
        if not section.get("selected", True):
            continue
        
        elements = section.get("elements", [])
        if not elements:
            continue
        
        # Get elements on each slide to normalize layout preferences
        selected_elements = [e for e in elements if e.get("selected", True)]
        for element in selected_elements:
            slide_num = element.get("config", {}).get("slide_number")
            if slide_num is None:
                continue
            
            # Normalize layout preference with slide number and total slides
            layout_preference = section.get("layout_preference")
            if layout_preference:
                normalized = _normalize_layout_preference(
                    layout_preference=layout_preference,
                    property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
                    slide_number=slide_num,
                    total_slides=total_slides,
                )
                # Store normalized preference in element config for orchestrator to use
                if normalized:
                    element.setdefault("config", {})["layout_preference_normalized"] = normalized
                else:
                    # Clear preference if it was ignored (first/last slide)
                    element.setdefault("config", {})["layout_preference_normalized"] = None
    
    # Third pass: Verify layout consistency (DO NOT CHANGE layouts, only verify and log)
    # Layouts were already correctly assigned during first pass using criteria
    print(f"\n{'='*60}")
    print(f"🎨 LAYOUT VERIFICATION (ALL ELEMENTS PER SLIDE)")
    print(f"{'='*60}\n")
    
    # Group all elements by slide number across all sections
    elements_by_slide: Dict[int, List[Dict[str, Any]]] = {}
    element_to_section: Dict[int, Dict[str, Any]] = {}  # Map element id to its section
    
    for section in sections:
        if not section.get("selected", True):
            continue
        
        elements = section.get("elements", [])
        selected_elements = [e for e in elements if e.get("selected", True)]
        
        for element in selected_elements:
            slide_num = element.get("config", {}).get("slide_number")
            if slide_num is None:
                continue
            
            # Track which section this element belongs to
            element_to_section[id(element)] = section
            
            if slide_num not in elements_by_slide:
                elements_by_slide[slide_num] = []
            elements_by_slide[slide_num].append(element)
    
    # Verify layouts for each slide (log only, do not change)
    for slide_num in sorted(elements_by_slide.keys()):
        slide_elements = elements_by_slide[slide_num]
        is_first_slide = slide_num == 1
        is_last_slide = slide_num == total_slides
        
        # Verify layout preferences are properly normalized for first/last slides
        for element in slide_elements:
            section = element_to_section.get(id(element))
            if section:
                layout_preference = section.get("layout_preference")
                if layout_preference and (is_first_slide or is_last_slide):
                    # Verify preference was ignored for first/last slides
                    normalized = _normalize_layout_preference(
                        layout_preference=layout_preference,
                        property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
                        slide_number=slide_num,
                        total_slides=total_slides,
                    )
                    if normalized:
                        # This shouldn't happen, but log if it does
                        slide_type = "first" if is_first_slide else "last"
                        print(f"   ⚠️  Slide {slide_num} ({slide_type}): Layout preference '{layout_preference}' should be ignored but normalized to '{normalized}'")
        
        # Log layout information for verification
        if slide_elements:
            element_types = [e.get("element_type", "unknown") for e in slide_elements]
            layouts = [e.get("config", {}).get("layout", "unknown") for e in slide_elements]
            print(f"   Slide {slide_num}: {len(slide_elements)} elements, types: {element_types}, layouts: {layouts}")
    
    print(f"{'='*60}\n")
    
    # Verification phase
    print(f"\n{'='*60}")
    print(f"🔍 SLIDE NUMBER VERIFICATION")
    print(f"{'='*60}")
    
    verification_results = []
    for section_idx, section in enumerate(sections):
        section_name = section.get("name", section.get("key", f"Section {section_idx}"))
        if not section.get("selected", True):
            continue
        
        elements = section.get("elements", [])
        for elem in elements:
            if not elem.get("selected", True):
                continue
            
            slide_num = elem.get("config", {}).get("slide_number")
            elem_type = elem.get("element_type", "unknown")
            elem_label = elem.get("label") or f"Element {elem.get('id', '?')}"
            
            verification_results.append({
                "section": section_name,
                "element": elem_label,
                "type": elem_type,
                "slide": slide_num
            })
            
            if slide_num is None:
                print(f"⚠️  {section_name} / {elem_label} ({elem_type}): NO SLIDE NUMBER!")
            else:
                print(f"✓  {section_name} / {elem_label} ({elem_type}): Slide {slide_num}")
    
    print(f"{'='*60}\n")
    
    # Final step: Ensure all elements meet minimum dimension requirements
    data = _ensure_minimum_dimensions_compliance(data)

    data = _apply_title_only_first_slide_slide_bump(data)

    return data


def _apply_title_only_first_slide_slide_bump(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reserve slide 1 for the cover/title template only: shift every element's
    slide_number by +1 and remap layouts that were assigned for the first-slide
    KPI row (base_slide) so content starts on slide 2 with a normal layout.

    Always applied because the rendering pipeline loads a first_slide template
    (cover) for every property_sub_type.  Content must never be rendered on top
    of the cover; it belongs on new slides starting at slide 2.
    """
    report = data.get("report") or {}

    property_sub_type = (
        (report.get("property_sub_type") or DEFAULT_PROPERTY_SUB_TYPE).strip().lower()
    )

    for section in data.get("sections", []):
        for el in section.get("elements", []):
            if not el.get("selected", True):
                continue
            cfg = el.setdefault("config", {})
            sn = cfg.get("slide_number")
            if sn is not None:
                cfg["slide_number"] = int(sn) + 1
            # base_slide is for the KPI/cover slide; content on slide 2+ must not stay base_slide
            if cfg.get("slide_number", 0) >= 2 and cfg.get("layout") == "base_slide":
                if property_sub_type == "figures":
                    cfg["layout"] = "grid_2x2"
                elif property_sub_type == "submarket":
                    cfg["layout"] = "grid"
                else:
                    cfg["layout"] = "full_width"

    print(
        "\n📌 title_only_first_slide: shifted all content to slide 2+ (slide 1 = title cover only)"
    )
    return data




def _normalize_layout_preference(
    layout_preference: Optional[str],
    property_sub_type: str,
    slide_number: Optional[int] = None,
    total_slides: Optional[int] = None,
) -> Optional[str]:
    """
    Normalize layout_preference string to a layout type.
    
    Maps UI strings like "Content (2x2 Grid)", "Full Width", etc. to
    layout types like "grid_2x2", "full_width", etc.
    
    Returns None if preference is invalid, not allowed for property_sub_type,
    or if provided for first/last slides (layout_preference only applies to middle slides).
    
    Args:
        layout_preference: The layout preference string from UI
        property_sub_type: The property sub type (figures, submarket, snapshot)
        slide_number: Current slide number (1-indexed)
        total_slides: Total number of slides in the presentation
    """
    if not layout_preference:
        return None
    
    # Check if layout_preference is provided for first or last slide
    # Layout preference is not allowed for 1st and last slides
    if slide_number is not None:
        if slide_number == 1:
            print(f"   ⚠️  Layout preference '{layout_preference}' ignored for first slide (only applies to middle slides)")
            return None
        if total_slides is not None and slide_number == total_slides:
            print(f"   ⚠️  Layout preference '{layout_preference}' ignored for last slide (only applies to middle slides)")
            return None
    
    # Normalize the preference string
    pref_lower = layout_preference.lower().strip()
    
    # Map common UI strings to layout types
    preference_map = {
        "content (2x2 grid)": "grid_2x2",
        "grid 2x2": "grid_2x2",
        "grid_2x2": "grid_2x2",
        "full width": "full_width",
        "full_width": "full_width",
        "base slide": "base_slide",
        "base_slide": "base_slide",
        # "first slide (base with kpis)" handled separately below
        "auto (smart layout)": None,  # Use default
        "auto": None,  # Use default
    }
    
    # "First Slide (Base with KPIs)" must map to base_slide so assignment
    # and rendering both target the dedicated first-slide template.
    if pref_lower == "first slide (base with kpis)":
        return "base_slide"
    
    # Check if preference maps to a layout type
    layout_type = preference_map.get(pref_lower)
    if layout_type is None and pref_lower not in preference_map:
        # Try direct match
        layout_type = pref_lower if pref_lower in ("grid_2x2", "full_width", "base_slide") else None
    
    if layout_type is None:
        return None  # Auto or unknown preference
    
    # Check if layout type is allowed for this property_sub_type
    allowed_types = get_allowed_layout_types(property_sub_type)
    if layout_type not in allowed_types:
        print(f"   ⚠️  Layout preference '{layout_preference}' -> '{layout_type}' not allowed for '{property_sub_type}'")
        print(f"      Allowed types: {allowed_types}")
        return None
    
    return layout_type


def _calculate_grid_elements_height(
    elements: List[Dict[str, Any]],
    layout: SlideLayoutMetrics,
    is_first_slide: bool = False
) -> float:
    """
    Calculate the total height taken by grid elements on a slide.
    Uses layout-aware height calculation for accuracy.
    
    For a 2x2 grid, the height is the maximum height of elements in each row.
    Row 0: elements at positions 0, 1
    Row 1: elements at positions 2, 3
    
    Args:
        elements: List of elements placed in grid layout
        layout: SlideLayoutMetrics with property_sub_type info
        is_first_slide: Whether this is the first slide
        
    Returns:
        Total height in inches taken by grid elements
    """
    if not elements:
        return 0.0
    
    # Identify first element by display_order (lowest value)
    first_element = None
    if elements:
        elements_with_order = [e for e in elements if e.get("display_order") is not None]
        if elements_with_order:
            first_element = min(elements_with_order, key=lambda e: e.get("display_order", 0))
        else:
            # Fallback to first element in list
            first_element = elements[0]
    
    # For 2x2 grid, calculate height of each row
    # Row 0: first 2 elements (positions 0, 1)
    # Row 1: next 2 elements (positions 2, 3)
    row_heights = []
    
    for row_idx in range(2):  # 2 rows in 2x2 grid
        row_elements = elements[row_idx * 2:(row_idx + 1) * 2]
        if not row_elements:
            break
        
        # Height of row is the maximum height of elements in that row
        max_row_height = 0.0
        for element in row_elements:
            # Check if this is the first element of the section
            is_first_element_of_section = (element is first_element)
            
            # Get element's assigned layout (could be grid_2x2 or full_width for tables)
            assigned_layout = element.get("config", {}).get("layout", "grid_2x2")
            # Use layout-aware height calculation
            element_height = _calculate_element_height_for_layout(
                element, assigned_layout, layout, is_first_slide,
                is_first_element_of_section=is_first_element_of_section
            )
            max_row_height = max(max_row_height, element_height)
        
        row_heights.append(max_row_height)
    
    # Total height = sum of row heights + gutter between rows
    total_height = sum(row_heights)
    if len(row_heights) > 1:
        total_height += layout.constraints.gutter_vertical
    
    return total_height


def _can_scale_to_fit_in_grid(
    element: Dict[str, Any],
    layout: SlideLayoutMetrics,
) -> bool:
    """
    Check if an element can be scaled down to fit in a grid quadrant while meeting minimum constraints.
    
    Args:
        element: Element dictionary
        layout: SlideLayoutMetrics with property_sub_type info
        
    Returns:
        True if element can be scaled to fit, False otherwise
    """
    from app.ppt_engine.ppt_helpers_utils.services.template_config import get_layout_threshold_config
    
    element_type = element.get("element_type", "")
    width, height = _estimate_element_size(element, layout, full_width=False)
    
    # Get threshold config for scaling
    threshold_config = get_layout_threshold_config(layout.property_sub_type)
    min_scale = threshold_config.min_scale_threshold_aggressive  # 40% minimum
    
    # Calculate scale factors needed
    scale_w = layout.quadrant_width / width if width > 0 else 1.0
    scale_h = layout.quadrant_height / height if height > 0 else 1.0
    scale_needed = min(scale_w, scale_h)
    
    # Check if scaling is within acceptable limits
    if scale_needed < min_scale:
        return False
    
    # Get element dimensions for minimum constraints
    element_dims = get_element_dimensions()
    
    # Check if scaled dimensions meet minimums
    scaled_width = width * scale_needed
    scaled_height = height * scale_needed
    
    if element_type == "chart":
        # Charts validated based on dynamic layout ratios
        # Height should be at least 20% of width (dynamic layout min from config)
        min_height = scaled_width * element_dims.dynamic_layout_min_height_ratio
        meets_min_height = scaled_height >= min_height * min_scale
        return meets_min_height
    elif element_type == "table":
        # Tables have more flexible constraints
        return True
    else:
        return True


def _calculate_section_total_height(
    selected_elements: List[Dict[str, Any]],
    layout: SlideLayoutMetrics,
    spacing: float = 0.2,
    layout_type: str = "full_width",
    is_first_slide: bool = False
) -> float:
    """
    Calculate total height needed for all elements in a section using layout-aware heights.
    Uses accurate height calculation based on actual layout widths.
    
    Args:
        selected_elements: List of selected elements in the section
        layout: SlideLayoutMetrics with property_sub_type info
        spacing: Spacing between elements in inches
        layout_type: Layout type to use for width calculation
        is_first_slide: Whether this is the first slide
        
    Returns:
        Total height needed including spacing between elements
    """
    if not selected_elements:
        return 0.0
    
    # Identify first element by display_order (lowest value)
    first_element = None
    if selected_elements:
        elements_with_order = [e for e in selected_elements if e.get("display_order") is not None]
        if elements_with_order:
            first_element = min(elements_with_order, key=lambda e: e.get("display_order", 0))
        else:
            # Fallback to first element in list
            first_element = selected_elements[0]
    
    total_height = 0.0
    for element in selected_elements:
        # Check if this is the first element of the section
        is_first_element_of_section = (element is first_element)
        
        # Use layout-aware height calculation
        element_height = _calculate_element_height_for_layout(
            element, layout_type, layout, is_first_slide, 
            is_first_element_of_section=is_first_element_of_section
        )
        total_height += element_height
        # Add spacing between elements (except for last element)
        if element != selected_elements[-1]:
            total_height += spacing
    
    return total_height


# ============================================================================
# SLIDE SHARING LOGIC (Strategy Pattern for Layout-Specific Rules)
# ============================================================================

def _check_full_width_sharing(
    slide_state: SlideState,
    layout_metrics: SlideLayoutMetrics,
) -> Tuple[bool, str]:
    """
    Check if a full_width section can share the current slide.
    
    Full-width layouts can share if there's sufficient vertical space available.
    """
    if slide_state.is_first_slide:
        return False, "cannot share first slide with full_width"
    
    # Use cumulative height from slide state
    if slide_state.cumulative_height > 0:
        estimated_existing_height = slide_state.cumulative_height
    else:
        # Fallback: estimate grid height based on number of elements
        grid_row_height = layout_metrics.quadrant_height + layout_metrics.constraints.gutter_vertical
        if slide_state.elements_count <= 2:
            estimated_existing_height = grid_row_height
        else:
            estimated_existing_height = grid_row_height * 2
    
    # Check if there's enough vertical space for at least one full_width element
    element_dims = get_element_dimensions()
    available_height = layout_metrics.content_height - estimated_existing_height
    min_element_height = element_dims.table_min_row_height * 3  # Minimum reasonable height
    
    if available_height >= min_element_height:
        return True, f"full_width allows vertical stacking (existing: {estimated_existing_height:.2f}\", available: {available_height:.2f}\")"
    return False, f"insufficient vertical space (existing: {estimated_existing_height:.2f}\", available: {available_height:.2f}\")"


def _check_grid_sharing(
    slide_state: SlideState,
    layout_metrics: SlideLayoutMetrics,
) -> Tuple[bool, str]:
    """
    Check if a grid_2x2 section can share the current slide.
    
    Grid layouts can share if a leftmost cell (positions 0 or 2 in a 2x2 grid) is available.
    
    In a 2x2 grid:
    - Cell 0 (top-left): leftmost ✓
    - Cell 1 (top-right): NOT leftmost
    - Cell 2 (bottom-left): leftmost ✓
    - Cell 3 (bottom-right): NOT leftmost
    
    New sections must start from leftmost cells, so sharing is allowed when:
    - elements_count == 0: cell 0 available (handled by empty slide check earlier)
    - elements_count == 1: skip cell 1, start at cell 2 (leftmost, bottom row)
    - elements_count == 2: cell 2 available (leftmost, bottom row)
    - elements_count == 3: cell 3 is next but NOT leftmost, cannot share
    """
    slide_capacity = layout_metrics.first_slide_capacity if slide_state.is_first_slide else layout_metrics.regular_slide_capacity
    
    # For grid, check if a leftmost cell is available
    # In a 2x2 grid, leftmost cells are at positions 0 and 2
    # 
    # When elements_count == 1:
    #   - Cell 0 is occupied, cell 1 is next sequentially BUT not leftmost
    #   - New section can SKIP cell 1 and start at cell 2 (leftmost of row 2)
    #   - This allows efficient use of slide space while respecting leftmost constraint
    #
    # When elements_count == 2:
    #   - Cells 0,1 are occupied, cell 2 is next AND leftmost
    #   - New section can start at cell 2
    
    if slide_state.elements_count in (1, 2):
        # Check if there's still capacity (cell 2 must be available)
        if slide_state.elements_count < slide_capacity:
            return True, f"grid sharing OK: {slide_state.elements_count} elements, new section starts at leftmost cell 2"
    
    # elements_count == 0 is handled by empty slide check earlier
    # elements_count == 3 means cell 3 is next but NOT leftmost, cannot share
    # elements_count >= 4 means slide is full
    return False, f"no leftmost cell available for grid layout (elements: {slide_state.elements_count})"


def _check_base_slide_sharing(
    slide_state: SlideState,
    layout_metrics: SlideLayoutMetrics,
) -> Tuple[bool, str]:
    """
    Check if a base_slide section can share the current slide.
    
    Base slide layouts use capacity-based sharing similar to grid.
    """
    slide_capacity = layout_metrics.first_slide_capacity if slide_state.is_first_slide else layout_metrics.regular_slide_capacity
    
    if slide_state.elements_count < slide_capacity:
        return True, f"capacity check: {slide_state.elements_count}/{slide_capacity}"
    
    return False, f"slide at capacity: {slide_state.elements_count}/{slide_capacity}"


# Config-driven layout sharing strategies (Open/Closed Principle)
LAYOUT_SHARING_STRATEGIES: Dict[str, Callable[[SlideState, SlideLayoutMetrics], Tuple[bool, str]]] = {
    "full_width": _check_full_width_sharing,
    "grid_2x2": _check_grid_sharing,
    "base_slide": _check_base_slide_sharing,
}


def _check_layout_specific_sharing(
    layout_type: str,
    slide_state: SlideState,
    layout_metrics: SlideLayoutMetrics,
) -> Tuple[bool, str]:
    """
    Delegate to layout-specific sharing check (Open/Closed Principle).
    
    This allows adding new layout types without modifying existing code.
    """
    strategy = LAYOUT_SHARING_STRATEGIES.get(layout_type)
    if strategy:
        return strategy(slide_state, layout_metrics)
    return False, f"unknown layout type: {layout_type}"


def _can_section_share_slide(
    slide_state: SlideState,
    new_section_layout: str,
    layout_metrics: SlideLayoutMetrics,
    incoming_elements: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, str]:
    """
    Determine if a new section can share the current slide.
    
    This function implements the core sharing logic:
    1. Empty slides can always accept new sections
    2. Layout compatibility is REQUIRED - different layouts go to new slides
    3. Layout-specific rules determine capacity/space sharing
    
    Args:
        slide_state: Current slide state
        new_section_layout: Layout type of the incoming section
        layout_metrics: Layout metrics for dimension calculations
        
    Returns:
        Tuple of (can_share: bool, reason: str)
    """
    # Empty slide can always accept new sections
    if slide_state.elements_count == 0:
        return True, "empty slide"
    
    # 2. Slide 1 Special Rule: Do not allow sharing with new sections
    # This ensures the first slide (which uses a special base template with KPIs)
    # remains focused on the primary section's content and avoids "extra charts"
    if slide_state.is_first_slide:
        return False, "first slide does not allow sharing with new sections"
    
    # Layout compatibility check (REQUIRED for sharing - no hybrid layouts)
    if not slide_state.can_accept_layout(new_section_layout):
        return False, f"layout mismatch (current: {slide_state.layout}, new: {new_section_layout})"
    
    # For full_width, do a concrete height check for the incoming section.
    # This prevents over-packing multiple full_width sections onto a single slide and avoids
    # downstream table continuations getting interleaved with later figures.
    if new_section_layout == "full_width" and incoming_elements:
        if slide_state.is_first_slide:
            return False, "cannot share first slide with full_width"

        existing_height = slide_state.cumulative_height
        if existing_height <= 0:
            # If we don't have an accurate height, be conservative and start a fresh slide.
            return False, "missing cumulative height for full_width sharing; starting fresh slide"

        # Account for the vertical gutter between stacked full_width sections.
        gutter = max(layout_metrics.constraints.gutter_vertical, 0.1)
        remaining_height = layout_metrics.content_height - existing_height - gutter

        # Compute the required height for this incoming section using the same
        # layout-aware height calculator used during assignment.
        # This includes section title space for the first element of the section.
        elements_sorted = sorted(incoming_elements, key=lambda e: e.get("display_order", 0))
        first_element = elements_sorted[0] if elements_sorted else None
        required_height = 0.0
        for idx, el in enumerate(elements_sorted):
            is_first_el = (el is first_element)
            el_h = _calculate_element_height_for_layout(
                el,
                "full_width",
                layout_metrics,
                is_first_slide=False,
                is_first_element_of_section=is_first_el,
            )
            if idx > 0:
                required_height += gutter
            required_height += el_h

        if required_height <= remaining_height:
            return True, (
                f"full_width share OK (existing: {existing_height:.2f}\", "
                f"remaining: {remaining_height:.2f}\", needed: {required_height:.2f}\")"
            )
        return False, (
            f"insufficient vertical space for full_width share (existing: {existing_height:.2f}\", "
            f"remaining: {remaining_height:.2f}\", needed: {required_height:.2f}\")"
        )

    # Delegate to layout-specific sharing rules
    return _check_layout_specific_sharing(new_section_layout, slide_state, layout_metrics)


def _assign_section_elements(
    section: Dict[str, Any],
    start_slide: int,
    elements_on_current_slide: int = 0,
    is_first_slide: bool = False,
    layout: SlideLayoutMetrics | None = None,
    layout_preference: Optional[str] = None,
    normalized_layout: Optional[str] = None,
    total_slides: Optional[int] = None,
    global_cumulative_height: float = 0.0,
    current_slide_layout: Optional[str] = None,
) -> tuple[int, int, bool, float, Optional[str]]:
    """
    Assign slide numbers to elements within a section.
    
    Args:
        section: Section dictionary with elements
        start_slide: Starting slide number
        elements_on_current_slide: Number of elements already on current slide
        is_first_slide: True if we're on the first slide
        layout: SlideLayoutMetrics with property_sub_type info
        layout_preference: Optional layout preference from section
        total_slides: Total number of slides (None during first pass)
        global_cumulative_height: Current cumulative height on the slide
        current_slide_layout: Layout type of the current slide (for sharing compatibility)
        
    Returns:
        Tuple of (current_slide, elements_on_current_slide, is_first_slide, cumulative_height, current_slide_layout)
    """
    elements = section.get("elements", [])
    
    # Sort elements by display_order
    elements.sort(key=lambda e: e.get("display_order", 0))
    
    # Filter selected elements
    selected_elements = [e for e in elements if e.get("selected", True)]
    
    if not selected_elements:
        return start_slide, elements_on_current_slide, is_first_slide, global_cumulative_height, current_slide_layout
    
    # Ensure layout is available
    layout = layout or _build_layout_metrics({"report": {}})
    
    # Pre-calculate optimal layouts for tables (before assignment)
    # This evaluates all possible layouts and selects the best one based on text wrapping
    allowed_layouts = get_allowed_layout_types(layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE)
    for element in selected_elements:
        if element.get("element_type") == "table":
            # Evaluate layouts and store best one
            best_layout_result = _evaluate_table_layouts(
                element=element,
                layout=layout,
                allowed_layouts=allowed_layouts,
                is_first_slide=is_first_slide and start_slide == 1
            )
            if best_layout_result:
                best_layout_type, _, _ = best_layout_result
                # Store in element config for later use
                element.setdefault("config", {})["_preferred_layout"] = best_layout_type
    
    # Determine layout type FIRST (before section boundary check)
    # Use normalized_layout if provided, otherwise determine from criteria
    # For first slide, layout preference is ignored, so use criteria
    was_first_slide_for_layout = is_first_slide and start_slide == 1
    if was_first_slide_for_layout:
        determined_layout = determine_layout_type_from_criteria(
            property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
            is_first_slide=True,
            normalized_preference=None,  # First slide ignores preferences
            elements=selected_elements,
        )
    else:
        # For middle slides, use normalized_layout if provided, otherwise use criteria
        determined_layout = determine_layout_type_from_criteria(
            property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
            is_first_slide=False,
            normalized_preference=normalized_layout,
            elements=selected_elements,
        )
    
    # SECTION BOUNDARY RULE: Check if new section can share the current slide
    # Using SlideState and _can_section_share_slide for cleaner logic
    # Key rule: Different layouts CANNOT share slides (no hybrid layouts)
    slide_state = SlideState(
        slide_number=start_slide,
        elements_count=elements_on_current_slide,
        is_first_slide=is_first_slide,
        cumulative_height=global_cumulative_height,
        layout=current_slide_layout,
    )
    
    can_share, share_reason = _can_section_share_slide(
        slide_state=slide_state,
        new_section_layout=determined_layout,
        layout_metrics=layout,
        incoming_elements=selected_elements,
    )
    
    if elements_on_current_slide > 0:
        if can_share:
            print(f"   ℹ️  Section can share slide {start_slide} - {share_reason}")
            current_slide = start_slide
        else:
            # New section needs fresh slide
            current_slide = start_slide + 1
            elements_on_current_slide = 0
            is_first_slide = False
            current_slide_layout = None  # Reset layout for new slide
            print(f"   ⚠️  Starting new section on fresh slide {current_slide} ({share_reason})")
    else:
        current_slide = start_slide
    
    # Re-determine layout if the boundary check moved us off the first slide.
    # The initial determination used is_first_slide=True which hardcodes base_slide,
    # but the section actually landed on a non-first slide. Re-compute using the
    # section's actual normalized preference so it gets the correct layout.
    if was_first_slide_for_layout and not is_first_slide:
        determined_layout = determine_layout_type_from_criteria(
            property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
            is_first_slide=False,
            normalized_preference=normalized_layout,
            elements=selected_elements,
        )
        print(f"   🔄 Re-determined layout after moving to slide {current_slide}: {determined_layout}")
    
    # Set the layout for the current slide (if not already set)
    if current_slide_layout is None:
        current_slide_layout = determined_layout
    
    # Determine capacity for current slide
    layout = layout or _build_layout_metrics({"report": {}})
    
    forced_layout_type = determined_layout
    if forced_layout_type:
        print(f"   🎯 Determined layout: {forced_layout_type} (from {'preference' if normalized_layout else 'criteria'})")
    
    # Reset cumulative_height if we moved to a new slide
    if current_slide != start_slide:
        cumulative_height = 0.0

    if is_first_slide:
        slide_capacity = layout.first_slide_capacity
        # For first slide, determine if it uses grid or full_width
        uses_grid_for_first = layout.property_sub_type in ("figures", "submarket")
    else:
        slide_capacity = layout.regular_slide_capacity
        uses_grid_for_first = False
    
    # Track elements on current slide for layout logic (element references)
    elements_on_current_slide_list = []
    current_slide_num = current_slide

    # Track slide_group from frontend so elements from different slides
    # are never packed onto the same backend slide.  Reset at each section
    # boundary because slide_group is the slideIdx *within* a section.
    _prev_slide_group: Optional[int] = None
    _section_id = section.get("id")
    # Track cumulative height for full_width vertical stacking
    # Only use global_cumulative_height if we're continuing on the same slide
    # If we moved to a new slide, cumulative_height was already reset at line 899
    if current_slide == start_slide and elements_on_current_slide > 0:
        # Continuing on the same slide with existing elements
        # Use the actual cumulative_height from previous sections
        if global_cumulative_height > 0:
            cumulative_height = global_cumulative_height
        # If global_cumulative_height is 0, estimate based on layout type
        elif forced_layout_type == "full_width":
            # Fallback: estimate grid height if we don't have actual height
            grid_row_height = layout.quadrant_height + layout.constraints.gutter_vertical
            if elements_on_current_slide <= 2:
                cumulative_height = grid_row_height
            else:
                cumulative_height = grid_row_height * 2
        else:
            cumulative_height = 0.0
        
        print(f"   Continuing on slide {current_slide} with existing height: {cumulative_height:.2f}\"")
    elif current_slide == start_slide and elements_on_current_slide == 0:
        # Starting fresh on this slide with no existing elements
        cumulative_height = 0.0
    
    # Track if current slide uses full_width layout
    current_slide_uses_full_width = False
    
    # Use the determined layout type directly - no need to re-determine
    # For base_slide layout, elements are positioned horizontally, so use grid-like capacity logic
    # For full_width layout, use vertical stacking logic
    # For grid_2x2 layout, use grid capacity logic
    
    # For full_width or base_slide layout: try to fit as many elements as possible on current slide
    # base_slide positions elements horizontally, so it uses capacity-based logic
    # full_width positions elements vertically, so it uses height-based logic
    if forced_layout_type == "full_width":
        current_slide_uses_full_width = True
        # Get element dimensions for height capping
        element_dims = get_element_dimensions()
        
        # Identify first element by display_order (lowest value)
        first_element = None
        if selected_elements:
            elements_with_order = [e for e in selected_elements if e.get("display_order") is not None]
            if elements_with_order:
                first_element = min(elements_with_order, key=lambda e: e.get("display_order"))
            else:
                # Fallback to first element in list
                first_element = selected_elements[0]
        
        # Try to fit elements one by one on current slide
        for elem_idx, element in enumerate(selected_elements):
            element_type = element.get("element_type", "")
            element_label = element.get("label") or element.get("config", {}).get("chart_name") or f"Element {elem_idx}"
            
            # Initialize config if not present
            if "config" not in element:
                element["config"] = {}
            
            # ── slide_group boundary: force a new slide when the frontend
            #    slide grouping changes (so user-defined slides are preserved) ──
            elem_slide_group = element.get("slide_group")
            if (elem_slide_group is not None
                    and _prev_slide_group is not None
                    and elem_slide_group != _prev_slide_group
                    and elements_on_current_slide > 0):
                if elements_on_current_slide_list:
                    _apply_layout_to_slide_elements(
                        elements_on_current_slide_list, layout, current_slide_num,
                        is_first_slide, forced_layout_type)
                current_slide += 1
                current_slide_num = current_slide
                elements_on_current_slide = 0
                elements_on_current_slide_list = []
                cumulative_height = 0.0
                is_first_slide = False
                slide_capacity = layout.regular_slide_capacity
                current_slide_layout = None
                print(f"      ⏩ slide_group boundary ({_prev_slide_group}→{elem_slide_group}): starting slide {current_slide}")
            _prev_slide_group = elem_slide_group

            # Check if this is the first element of the section
            is_first_element_of_section = (element is first_element)
            
            # Use layout-aware height calculation for accurate height
            element_height = _calculate_element_height_for_layout(
                element, "full_width", layout, is_first_slide,
                is_first_element_of_section=is_first_element_of_section
            )
            
            # Add spacing between elements - use gutter_vertical from constraints to match orchestrator
            gutter = max(layout.constraints.gutter_vertical, 0.1)  # Match orchestrator's logic
            spacing = gutter if (elem_idx > 0 or elements_on_current_slide > 0) else 0.0
            total_height_needed = cumulative_height + spacing + element_height
            
            # Check if element fits vertically (with tolerance from config)
            element_dims = get_element_dimensions()
            
            # FIXED: For first slide, use actual available height from first_slide_start_top to bottom margin
            # not the regular content_height which uses different margins
            if is_first_slide and layout.layout_config.first_slide_start_top is not None:
                # Calculate actual available height for first slide
                first_slide_margin_bottom = (
                    layout.layout_config.first_slide_margin_bottom or 
                    layout.layout_config.base_constraints.margin_bottom
                )
                available_height = (
                    layout.constraints.slide_height - 
                    layout.layout_config.first_slide_start_top - 
                    first_slide_margin_bottom
                )
            else:
                # Regular slide uses standard content_height
                available_height = layout.content_height
            
            # No buffer needed - height calculations should be accurate now that we're using
            # the correct width for first slide calculations
            
            # Check if element fits AND has reasonable minimum space
            # For tables, ensure they get at least minimum reasonable height to avoid over-compression
            remaining_space = available_height - cumulative_height - spacing
            min_reasonable_height = element_height * 0.5  # Element needs at least 50% of its natural height
            
            # For tables specifically, enforce stricter minimum based on row count
            if element_type == "table":
                # Tables need minimum row height * number of rows
                table_data = element.get("config", {}).get("table_data", [])
                if table_data:
                    # Use configurable minimum rows (header + data rows) from element_dims
                    min_rows = min(len(table_data) + 1, element_dims.table_min_rows_before_overflow)
                    min_table_height = min_rows * element_dims.table_min_row_height * 1.3  # With padding
                    # Add label/source space
                    min_table_height += 0.5  # approximate label + source space
                    min_reasonable_height = max(min_reasonable_height, min_table_height)
            
            # For full-width layouts with content-based height calculation, use strict fit check (no tolerance)
            # since heights are now accurately calculated
            fits_with_tolerance = total_height_needed <= available_height  # No tolerance multiplier
            
            # has_reasonable_space: element should have at least its actual height OR the min_reasonable_height
            # If element fits its actual height, it's reasonable by definition (no compression needed)
            has_reasonable_space = remaining_space >= min(element_height, min_reasonable_height)
            
            # Check if overflow is allowed for full_width layouts
            # When overflow is enabled, oversized elements stay on current slide and will be split
            # during rendering (rendering creates continuation slides as needed)
            allow_overflow = element_dims.allow_full_width_overflow
            
            # For full_width layouts with overflow: keep element on current slide even if it doesn't fit
            # The rendering phase will handle splitting across slides
            # DEBUG: trace decision for each element
            print(f"      [DEBUG DECISION] {element_label}: fits={fits_with_tolerance}, allow_overflow={allow_overflow}, has_reasonable={has_reasonable_space}, remaining={remaining_space:.2f}, min_reasonable={min_reasonable_height:.2f}, total_needed={total_height_needed:.2f}, available={available_height:.2f}")
            if fits_with_tolerance and has_reasonable_space:
                # Element fits on current slide with reasonable space
                element["config"]["slide_number"] = current_slide
                element["config"]["layout"] = forced_layout_type if forced_layout_type else "full_width"
                elements_on_current_slide += 1
                elements_on_current_slide_list.append(element)
                cumulative_height = total_height_needed
                
                print(f"      [{current_slide}] {element_type} '{element_label}' (FULL WIDTH - fits, height: {element_height:.2f}\", total: {cumulative_height:.2f}\")")
            elif allow_overflow and has_reasonable_space:
                # OVERFLOW MODE: Element doesn't fit completely but overflow is enabled
                # AND there's at least minimum reasonable space for a partial render
                # Keep element on current slide - it will be split during rendering
                element["config"]["slide_number"] = current_slide
                element["config"]["layout"] = forced_layout_type if forced_layout_type else "full_width"
                element["config"]["_needs_split"] = True  # Mark for splitting during render
                element["config"]["_available_height"] = remaining_space  # Store remaining space for render phase
                elements_on_current_slide += 1
                elements_on_current_slide_list.append(element)
                # Use available_height as cumulative since element will be split
                cumulative_height = available_height
                
                print(f"      [{current_slide}] {element_type} '{element_label}' (FULL WIDTH - SPLIT, needs: {element_height:.2f}\", available: {remaining_space:.2f}\")")
            else:
                # Element doesn't fit on current slide AND doesn't have minimum reasonable space
                # (either overflow is disabled OR remaining space < min_reasonable_height)
                # DEBUG: trace why element is moving to next slide
                print(f"      [DEBUG] {element_type} '{element_label}' NOT SPLIT: allow_overflow={allow_overflow}, has_reasonable_space={has_reasonable_space}, remaining={remaining_space:.2f}, min_reasonable={min_reasonable_height:.2f}")
                if not has_reasonable_space and fits_with_tolerance:
                    print(f"      [{current_slide}] {element_type} '{element_label}' - MOVED TO NEXT SLIDE (would be over-compressed: {remaining_space:.2f}\" < {min_reasonable_height:.2f}\" min)")
                
                # Apply layout to elements already on current slide before moving
                if elements_on_current_slide_list:
                    _apply_layout_to_slide_elements(elements_on_current_slide_list, layout, current_slide_num, is_first_slide, forced_layout_type)
                
                # Track if we're leaving the first slide
                was_first_slide = is_first_slide
                
                # Move to next slide
                current_slide += 1
                current_slide_num = current_slide
                elements_on_current_slide = 0
                elements_on_current_slide_list = []
                cumulative_height = 0.0
                is_first_slide = False
                slide_capacity = layout.regular_slide_capacity
                current_slide_layout = None  # Reset layout for new slide
                
                # Re-determine layout if transitioning from first slide to continuation slide
                # Use criteria-based determination (ignore layout_preference for continuation slides)
                if was_first_slide:
                    forced_layout_type = determine_layout_type_from_criteria(
                        property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
                        is_first_slide=False,
                        normalized_preference=None,  # Force criteria-based determination for continuation slides
                        elements=selected_elements[elem_idx:],  # Remaining elements
                    )
                    print(f"   🔄 Transitioned from first slide to continuation slide - layout changed to: {forced_layout_type}")
                
                # Set layout for new slide
                current_slide_layout = forced_layout_type if forced_layout_type else "full_width"
                
                # Check if overflow is enabled for the new slide
                if allow_overflow:
                    # With overflow enabled, place element on new slide and mark for splitting if needed
                    element["config"]["slide_number"] = current_slide
                    element["config"]["layout"] = forced_layout_type if forced_layout_type else "full_width"
                    
                    # Recalculate available height for new slide (non-first slide)
                    new_slide_available_height = layout.content_height
                    if element_height > new_slide_available_height:
                        element["config"]["_needs_split"] = True
                        element["config"]["_available_height"] = new_slide_available_height
                        cumulative_height = new_slide_available_height
                        print(f"      [{current_slide}] {element_type} '{element_label}' (FULL WIDTH - OVERFLOW TO NEXT SLIDE, needs: {element_height:.2f}\", available: {new_slide_available_height:.2f}\")")
                    else:
                        cumulative_height = element_height
                        print(f"      [{current_slide}] {element_type} '{element_label}' (FULL WIDTH - new slide, height: {element_height:.2f}\")")
                    
                    elements_on_current_slide = 1
                    elements_on_current_slide_list = [element]
                else:
                    # No overflow - old behavior
                    element["config"]["slide_number"] = current_slide
                    element["config"]["layout"] = forced_layout_type if forced_layout_type else "full_width"
                    elements_on_current_slide = 1
                    elements_on_current_slide_list = [element]
                    cumulative_height = element_height
                    
                    print(f"      [{current_slide}] {element_type} '{element_label}' (FULL WIDTH - new slide, height: {element_height:.2f}\")")
        
        # Apply layout to remaining elements on current slide
        if elements_on_current_slide_list:
            _apply_layout_to_slide_elements(elements_on_current_slide_list, layout, current_slide_num, is_first_slide, forced_layout_type)
        
        # Return - all elements processed
        return current_slide, elements_on_current_slide, is_first_slide, cumulative_height, current_slide_layout
    
    # For base_slide layout: elements are positioned horizontally (like grid), use capacity-based logic
    if forced_layout_type == "base_slide":
        # Keep first base_slide focused on visual/KPI content.
        # Commentary/text is deferred to continuation slides when visual elements exist.
        prioritized_elements = selected_elements
        if is_first_slide and current_slide == 1:
            non_text_elements = [
                e for e in selected_elements
                if (e.get("element_type") or "").lower() not in {"commentary", "text", "title"}
            ]
            text_like_elements = [
                e for e in selected_elements
                if (e.get("element_type") or "").lower() in {"commentary", "text", "title"}
            ]
            if non_text_elements and text_like_elements:
                prioritized_elements = non_text_elements + text_like_elements
                print(
                    f"   ℹ️  First base_slide: deferred {len(text_like_elements)} text/commentary block(s) after visual elements"
                )

        # base_slide positions elements horizontally, so use capacity-based assignment
        # This is similar to grid layout but with different positioning
        for elem_idx, element in enumerate(prioritized_elements):
            element_type = element.get("element_type", "")
            element_label = element.get("label") or element.get("config", {}).get("chart_name") or f"Element {elem_idx}"
            
            # Initialize config if not present
            if "config" not in element:
                element["config"] = {}
            
            # ── slide_group boundary ──
            elem_slide_group = element.get("slide_group")
            if (elem_slide_group is not None
                    and _prev_slide_group is not None
                    and elem_slide_group != _prev_slide_group
                    and elements_on_current_slide > 0):
                _apply_layout_to_slide_elements(
                    elements_on_current_slide_list, layout, current_slide_num,
                    is_first_slide, forced_layout_type)
                current_slide += 1
                current_slide_num = current_slide
                elements_on_current_slide = 0
                elements_on_current_slide_list = []
                cumulative_height = 0.0
                is_first_slide = False
                slide_capacity = layout.regular_slide_capacity
                current_slide_layout = None
                print(f"      ⏩ slide_group boundary ({_prev_slide_group}→{elem_slide_group}): starting slide {current_slide}")
            _prev_slide_group = elem_slide_group

            # base_slide uses capacity-based logic (elements positioned horizontally)
            if elements_on_current_slide < slide_capacity:
                element["config"]["slide_number"] = current_slide
                element["config"]["layout"] = "base_slide"
                elements_on_current_slide += 1
                elements_on_current_slide_list.append(element)
                print(f"      [{current_slide}] {element_type} '{element_label}' (BASE_SLIDE - slot {elements_on_current_slide}/{slide_capacity})")
            else:
                # Current slide is full, apply layout and move to next
                _apply_layout_to_slide_elements(elements_on_current_slide_list, layout, current_slide_num, is_first_slide, forced_layout_type)
                
                # Track if we're leaving the first slide
                was_first_slide = is_first_slide
                
                current_slide += 1
                current_slide_num = current_slide
                elements_on_current_slide = 1
                elements_on_current_slide_list = [element]
                cumulative_height = 0.0
                is_first_slide = False
                slide_capacity = layout.regular_slide_capacity
                current_slide_layout = None  # Reset layout for new slide
                
                # Re-determine layout if transitioning from first slide to continuation slide
                # Use criteria-based determination (ignore layout_preference for continuation slides)
                if was_first_slide:
                    forced_layout_type = determine_layout_type_from_criteria(
                        property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
                        is_first_slide=False,
                        normalized_preference=None,  # Force criteria-based determination for continuation slides
                        elements=prioritized_elements[elem_idx:],  # Remaining elements
                    )
                    print(f"   🔄 Transitioned from first slide to continuation slide - layout changed to: {forced_layout_type}")
                
                # Set layout for new slide
                current_slide_layout = forced_layout_type if forced_layout_type else "base_slide"
                
                element["config"]["slide_number"] = current_slide
                element["config"]["layout"] = current_slide_layout
                print(f"      [{current_slide}] {element_type} '{element_label}' (BASE_SLIDE - slot 1/{slide_capacity})")
        
        # Apply layout to remaining elements on current slide
        if elements_on_current_slide_list:
            _apply_layout_to_slide_elements(elements_on_current_slide_list, layout, current_slide_num, is_first_slide, forced_layout_type)
        
        return current_slide, elements_on_current_slide, is_first_slide, cumulative_height, current_slide_layout
    
    # For grid_2x2 layout: use grid capacity-based logic
    # Determine if we should use grid layout
    if forced_layout_type == "grid_2x2":
        uses_grid = True
    elif forced_layout_type is None:
        # No layout determined, use property_sub_type rules
        uses_grid = layout.property_sub_type in ("figures", "submarket")
    else:
        # Other layout types (full_width, base_slide) already handled above
        uses_grid = False
    
    # Grid layout logic (for grid_2x2 or when no specific layout determined and property_sub_type uses grid)
    if uses_grid:
        # Identify first element by display_order (lowest value)
        first_element = None
        if selected_elements:
            elements_with_order = [e for e in selected_elements if e.get("display_order") is not None]
            if elements_with_order:
                first_element = min(elements_with_order, key=lambda e: e.get("display_order"))
            else:
                # Fallback to first element in list
                first_element = selected_elements[0]
        
        for elem_idx, element in enumerate(selected_elements):
            element_type = element.get("element_type", "")
            element_label = element.get("label") or element.get("config", {}).get("chart_name") or f"Element {elem_idx}"
            
            # Initialize config if not present
            if "config" not in element:
                element["config"] = {}
            
            # ── slide_group boundary ──
            elem_slide_group = element.get("slide_group")
            if (elem_slide_group is not None
                    and _prev_slide_group is not None
                    and elem_slide_group != _prev_slide_group
                    and elements_on_current_slide > 0):
                if elements_on_current_slide_list:
                    _apply_layout_to_slide_elements(
                        elements_on_current_slide_list, layout, current_slide_num,
                        is_first_slide, forced_layout_type)
                current_slide += 1
                current_slide_num = current_slide
                elements_on_current_slide = 0
                elements_on_current_slide_list = []
                cumulative_height = 0.0
                is_first_slide = False
                slide_capacity = layout.regular_slide_capacity
                current_slide_layout = None
                print(f"      ⏩ slide_group boundary ({_prev_slide_group}→{elem_slide_group}): starting slide {current_slide}")
            _prev_slide_group = elem_slide_group

            # Check if this is the first element of the section
            is_first_element_of_section = (element is first_element)
            
            can_fit = _can_fit_in_quadrant(element, layout) if uses_grid else True
            
            # Check if element can be scaled to fit in grid (for charts)
            can_scale_to_fit = False
            if uses_grid and element_type == "chart" and not can_fit:
                can_scale_to_fit = _can_scale_to_fit_in_grid(element, layout)
            
            # Also check if element can meet minimum dimensions in grid layout
            can_meet_minimums_in_grid = True
            if uses_grid and element_type in ["chart", "table", "commentary"]:
                can_meet_minimums_in_grid = _validate_element_minimum_dimensions(element, layout, "grid_2x2")
            
            # IMPORTANT: Grid layouts use TRIMMING to fit large elements
            # Large elements in grid layouts should stay in grid and be trimmed/scaled
            # They should NOT be promoted to full_width
            # 
            # Only promote to full_width if minimum dimensions can't be met
            # (e.g., element would be too small to read if scaled down)
            needs_full_slide = (
                not can_meet_minimums_in_grid  # Only promote if min dimensions can't be met
            ) and element_type in ["chart", "table"] and uses_grid
            
            # Log when large elements will be trimmed in grid
            if uses_grid and not can_fit and not needs_full_slide and element_type in ["chart", "table"]:
                print(f"      📐 Large element '{element_label}' will be trimmed to fit in grid layout")
            
            # Commentary can overflow vertically, tables can overflow horizontally
            # So they don't necessarily need a full slide
            if element_type == "commentary":
                needs_full_slide = False  # Commentary can share and overflow vertically
            
            # Decide placement
            if needs_full_slide:
                # Element needs its own slide (too large for grid or doesn't meet min dimensions)
                reason = "too large for grid" if not can_fit else "minimum dimensions not met in grid"
                
                # Check if we need to move to next slide FIRST
                # This happens when: 1) there are other elements on current slide, OR
                # 2) This is the first slide with FULL_WIDTH layout and the element won't fit
                # NOTE: For GRID layouts, elements stay on slide and get trimmed/scaled - no overflow
                should_move_to_new_slide = elements_on_current_slide > 0
                
                # IMPORTANT: Only check for overflow in FULL_WIDTH layouts
                # Grid layouts use trimming/scaling to fit elements - they don't overflow
                # Full width layouts allow overflow to next slide
                element_dims = get_element_dimensions()
                is_full_width_layout = forced_layout_type in {"full_width", "base_slide"} or (
                    not uses_grid and element_dims.allow_full_width_overflow
                )
                
                # For first slide with full_width layout, check if element fits
                if not should_move_to_new_slide and is_first_slide and element_type in ["table", "chart"] and is_full_width_layout:
                    # Calculate actual available height on first slide
                    first_slide_margin_bottom = (
                        layout.layout_config.first_slide_margin_bottom or 
                        layout.layout_config.base_constraints.margin_bottom
                    )
                    first_slide_available_height = (
                        layout.constraints.slide_height - 
                        layout.layout_config.first_slide_start_top - 
                        first_slide_margin_bottom
                    )
                    
                    # Calculate element height with layout-aware calculation
                    element_height = _calculate_element_height_for_layout(
                        element, "full_width", layout, is_first_slide=True,
                        is_first_element_of_section=is_first_element_of_section
                    )
                    
                    # If element is too tall for first slide, move to next slide (full_width only)
                    if element_height > first_slide_available_height:
                        should_move_to_new_slide = True
                        print(f"      ⚠️ Element {element_label} ({element_height:.2f}\") too large for first slide ({first_slide_available_height:.2f}\" available) - moving to slide 2 (full_width overflow)")
                elif not should_move_to_new_slide and is_first_slide and element_type in ["table", "chart"] and not is_full_width_layout:
                    # Grid layout: element stays on slide 1, will be trimmed/scaled to fit
                    print(f"      📐 Element {element_label} will be trimmed/scaled to fit in grid layout on slide 1")
                
                if should_move_to_new_slide:
                    if elements_on_current_slide > 0:
                        # Apply layout to previous slide's elements before moving
                        _apply_layout_to_slide_elements(elements_on_current_slide_list, layout, current_slide_num, is_first_slide, forced_layout_type)
                    
                    # Track if we're leaving the first slide
                    was_first_slide = is_first_slide
                    
                    current_slide += 1
                    current_slide_num = current_slide
                    elements_on_current_slide = 0
                    elements_on_current_slide_list = []
                    cumulative_height = 0.0
                    is_first_slide = False
                    slide_capacity = layout.regular_slide_capacity
                    current_slide_layout = None  # Reset layout for new slide
                    
                    # Re-determine layout if transitioning from first slide to continuation slide
                    # Use criteria-based determination (ignore layout_preference for continuation slides)
                    if was_first_slide:
                        forced_layout_type = determine_layout_type_from_criteria(
                            property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
                            is_first_slide=False,
                            normalized_preference=None,  # Force criteria-based determination for continuation slides
                            elements=selected_elements[elem_idx:],  # Remaining elements
                        )
                        print(f"   🔄 Transitioned from first slide to continuation slide - layout changed to: {forced_layout_type}")
                
                element["config"]["slide_number"] = current_slide
                # Use pre-calculated preferred layout for tables, otherwise use forced_layout_type or default to full_width
                if element_type == "table" and element.get("config", {}).get("_preferred_layout"):
                    element["config"]["layout"] = element["config"]["_preferred_layout"]
                    current_slide_layout = element["config"]["_preferred_layout"]
                else:
                    element["config"]["layout"] = forced_layout_type if forced_layout_type else "full_width"
                    current_slide_layout = forced_layout_type if forced_layout_type else "full_width"
                print(f"      [{current_slide}] {element_type} '{element_label}' (FULL WIDTH - {reason})")
                
                # Track if we're leaving the first slide
                was_first_slide = is_first_slide
                
                # Move to next slide after this full-slide element
                current_slide += 1
                current_slide_num = current_slide
                elements_on_current_slide = 0
                elements_on_current_slide_list = []
                cumulative_height = 0.0  # Reset for new slide
                is_first_slide = False
                slide_capacity = layout.regular_slide_capacity
                current_slide_layout = None  # Reset layout for new slide
                
                # Re-determine layout if transitioning from first slide to continuation slide
                # Use criteria-based determination (ignore layout_preference for continuation slides)
                if was_first_slide:
                    forced_layout_type = determine_layout_type_from_criteria(
                        property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
                        is_first_slide=False,
                        normalized_preference=None,  # Force criteria-based determination for continuation slides
                        elements=selected_elements[elem_idx+1:],  # Remaining elements (current element already placed)
                    )
                    print(f"   🔄 Transitioned from first slide to continuation slide - layout changed to: {forced_layout_type}")
                
            elif elements_on_current_slide < slide_capacity:
                # Element fits on current slide (grid layout) or can be scaled to fit
                element["config"]["slide_number"] = current_slide
                # Use pre-calculated preferred layout for tables, otherwise use forced_layout_type or grid_2x2
                if element_type == "table" and element.get("config", {}).get("_preferred_layout"):
                    element["config"]["layout"] = element["config"]["_preferred_layout"]
                else:
                    element["config"]["layout"] = forced_layout_type if forced_layout_type else "grid_2x2"
                elements_on_current_slide += 1
                elements_on_current_slide_list.append(element)
                
                # Calculate and update cumulative height for grid elements using layout-aware calculation
                # Grid height is the maximum height of the current row
                assigned_layout = element.get("config", {}).get("layout", "grid_2x2")
                # Use layout-aware height calculation
                element_height = _calculate_element_height_for_layout(
                    element, assigned_layout, layout, is_first_slide,
                    is_first_element_of_section=is_first_element_of_section
                )
                # For grid, height is per row (max of elements in row)
                # If we're in row 0 (elements 0-1) or row 1 (elements 2-3)
                current_row = (elements_on_current_slide - 1) // 2
                if current_row == 0:
                    # First row: update cumulative height to max of row 0 elements
                    row_0_elements = elements_on_current_slide_list[:min(2, len(elements_on_current_slide_list))]
                    max_row_height = max(
                        _calculate_element_height_for_layout(
                            e, e.get("config", {}).get("layout", "grid_2x2"), layout, is_first_slide,
                            is_first_element_of_section=(e is first_element)
                        )
                        for e in row_0_elements
                    )
                    cumulative_height = max_row_height
                elif current_row == 1:
                    # Second row: add row 1 height + gutter
                    row_1_elements = elements_on_current_slide_list[2:]
                    if row_1_elements:
                        max_row_1_height = max(
                            _calculate_element_height_for_layout(
                                e, e.get("config", {}).get("layout", "grid_2x2"), layout, is_first_slide,
                                is_first_element_of_section=(e is first_element)
                            )
                            for e in row_1_elements
                        )
                        row_0_elements = elements_on_current_slide_list[:2]
                        max_row_0_height = max(
                            _calculate_element_height_for_layout(
                                e, e.get("config", {}).get("layout", "grid_2x2"), layout, is_first_slide,
                                is_first_element_of_section=(e is first_element)
                            )
                            for e in row_0_elements
                        ) if row_0_elements else 0.0
                        cumulative_height = max_row_0_height + layout.constraints.gutter_vertical + max_row_1_height
                
                # Check if minimum dimensions will be met in grid layout
                grid_compliant = _validate_element_minimum_dimensions(element, layout, "grid_2x2") if uses_grid else True
                scale_note = " [scaled to fit]" if can_scale_to_fit else ""
                compliance_note = "" if grid_compliant else " [⚠️ min dims]"
                
                print(f"      [{current_slide}] {element_type} '{element_label}' (GRID_2X2 - slot {elements_on_current_slide}/{slide_capacity}){scale_note}{compliance_note}")
                
                # If current slide is full, apply layout and move to next
                if elements_on_current_slide >= slide_capacity:
                    _apply_layout_to_slide_elements(elements_on_current_slide_list, layout, current_slide_num, is_first_slide, forced_layout_type)
                    # Calculate final grid height before moving to next slide
                    cumulative_height = _calculate_grid_elements_height(elements_on_current_slide_list, layout, is_first_slide)
                    
                    # Track if we're leaving the first slide
                    was_first_slide = is_first_slide
                    
                    current_slide += 1
                    current_slide_num = current_slide
                    elements_on_current_slide = 0
                    elements_on_current_slide_list = []
                    cumulative_height = 0.0  # Reset for new slide
                    is_first_slide = False
                    slide_capacity = layout.regular_slide_capacity
                    current_slide_uses_full_width = False
                    current_slide_layout = None  # Reset layout for new slide
                    
                    # Re-determine layout if transitioning from first slide to continuation slide
                    # Use criteria-based determination (ignore layout_preference for continuation slides)
                    if was_first_slide:
                        forced_layout_type = determine_layout_type_from_criteria(
                            property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
                            is_first_slide=False,
                            normalized_preference=None,  # Force criteria-based determination for continuation slides
                            elements=selected_elements[elem_idx+1:],  # Remaining elements (current element already placed)
                        )
                        print(f"   🔄 Transitioned from first slide to continuation slide - layout changed to: {forced_layout_type}")
                        
                        # If layout changed to full_width, process remaining elements with full_width logic
                        if forced_layout_type == "full_width":
                            current_slide_layout = "full_width"  # Set layout for new slide
                            # Process remaining elements with full_width stacking logic
                            remaining_elements = selected_elements[elem_idx+1:]
                            for remaining_idx, remaining_elem in enumerate(remaining_elements):
                                elem_type = remaining_elem.get("element_type", "")
                                elem_label = remaining_elem.get("label") or remaining_elem.get("config", {}).get("chart_name") or f"Element {elem_idx+1+remaining_idx}"
                                
                                if "config" not in remaining_elem:
                                    remaining_elem["config"] = {}
                                
                                # Check if this is the first element of the section
                                is_first_elem = (remaining_elem is first_element)
                                
                                # Calculate element height
                                elem_height = _calculate_element_height_for_layout(
                                    remaining_elem, "full_width", layout, False,
                                    is_first_element_of_section=is_first_elem
                                )
                                
                                # Add spacing between elements
                                gutter = max(layout.constraints.gutter_vertical, 0.1)
                                spacing = gutter if elements_on_current_slide > 0 else 0.0
                                total_height_needed = cumulative_height + spacing + elem_height
                                
                                # Use same comprehensive logic as main full_width handler
                                element_dims = get_element_dimensions()
                                available_height = layout.content_height
                                remaining_space = available_height - cumulative_height - spacing
                                
                                # Calculate min_reasonable_height (same as main handler)
                                min_reasonable_height = elem_height * 0.5
                                
                                # For tables, enforce stricter minimum based on row count
                                if elem_type == "table":
                                    table_data = remaining_elem.get("config", {}).get("table_data", [])
                                    if table_data:
                                        min_rows = min(len(table_data) + 1, element_dims.table_min_rows_before_overflow)
                                        min_table_height = min_rows * element_dims.table_min_row_height * 1.3 + 0.5
                                        min_reasonable_height = max(min_reasonable_height, min_table_height)
                                
                                fits_with_tolerance = total_height_needed <= available_height
                                has_reasonable_space = remaining_space >= min(elem_height, min_reasonable_height)
                                allow_overflow = element_dims.allow_full_width_overflow
                                
                                print(f"      [DEBUG DECISION TRANSITION2] {elem_label}: fits={fits_with_tolerance}, allow_overflow={allow_overflow}, has_reasonable={has_reasonable_space}, remaining={remaining_space:.2f}, min_reasonable={min_reasonable_height:.2f}, total_needed={total_height_needed:.2f}, available={available_height:.2f}")
                                
                                if fits_with_tolerance and has_reasonable_space:
                                    # Element fits on current slide with reasonable space
                                    remaining_elem["config"]["slide_number"] = current_slide
                                    remaining_elem["config"]["layout"] = "full_width"
                                    elements_on_current_slide += 1
                                    cumulative_height = total_height_needed
                                    print(f"      [{current_slide}] {elem_type} '{elem_label}' (FULL WIDTH - fits, height: {elem_height:.2f}\", total: {cumulative_height:.2f}\")")
                                elif allow_overflow and has_reasonable_space:
                                    # Element doesn't fit but there's reasonable space for partial render
                                    remaining_elem["config"]["slide_number"] = current_slide
                                    remaining_elem["config"]["layout"] = "full_width"
                                    remaining_elem["config"]["_needs_split"] = True
                                    remaining_elem["config"]["_available_height"] = remaining_space
                                    elements_on_current_slide += 1
                                    cumulative_height = available_height
                                    print(f"      [{current_slide}] {elem_type} '{elem_label}' (FULL WIDTH - SPLIT, needs: {elem_height:.2f}\", available: {remaining_space:.2f}\")")
                                else:
                                    # Element doesn't fit AND not enough space for split, move to next slide
                                    current_slide += 1
                                    current_slide_layout = "full_width"
                                    elements_on_current_slide = 1
                                    remaining_elem["config"]["slide_number"] = current_slide
                                    remaining_elem["config"]["layout"] = "full_width"
                                    
                                    # Check if element needs split on new slide
                                    new_slide_available = layout.content_height
                                    if elem_height > new_slide_available:
                                        remaining_elem["config"]["_needs_split"] = True
                                        remaining_elem["config"]["_available_height"] = new_slide_available
                                        cumulative_height = new_slide_available
                                        print(f"      [{current_slide}] {elem_type} '{elem_label}' (FULL WIDTH - OVERFLOW TO NEXT SLIDE, needs: {elem_height:.2f}\", available: {new_slide_available:.2f}\")")
                                    else:
                                        cumulative_height = elem_height
                                        print(f"      [{current_slide}] {elem_type} '{elem_label}' (FULL WIDTH - new slide, height: {elem_height:.2f}\")")
                            
                            # All remaining elements processed, break out of grid loop
                            break
            else:
                # Current slide is full, apply layout and move to next
                _apply_layout_to_slide_elements(elements_on_current_slide_list, layout, current_slide_num, is_first_slide, forced_layout_type)
                # Calculate grid height before moving
                if elements_on_current_slide_list:
                    cumulative_height = _calculate_grid_elements_height(elements_on_current_slide_list, layout, is_first_slide)
                
                # Track if we're leaving the first slide
                was_first_slide = is_first_slide
                
                current_slide += 1
                current_slide_num = current_slide
                elements_on_current_slide = 1
                elements_on_current_slide_list = [element]
                cumulative_height = 0.0  # Reset for new slide
                is_first_slide = False
                slide_capacity = layout.regular_slide_capacity
                current_slide_uses_full_width = False
                current_slide_layout = None  # Reset layout for new slide
                
                # Re-determine layout if transitioning from first slide to continuation slide
                # Use criteria-based determination (ignore layout_preference for continuation slides)
                if was_first_slide:
                    forced_layout_type = determine_layout_type_from_criteria(
                        property_sub_type=layout.property_sub_type or DEFAULT_PROPERTY_SUB_TYPE,
                        is_first_slide=False,
                        normalized_preference=None,  # Force criteria-based determination for continuation slides
                        elements=selected_elements[elem_idx:],  # Remaining elements
                    )
                    print(f"   🔄 Transitioned from first slide to continuation slide - layout changed to: {forced_layout_type}")
                    
                    # If layout changed to full_width, process remaining elements with full_width logic
                    if forced_layout_type == "full_width":
                        current_slide_layout = "full_width"  # Set layout for new slide
                        # Process current and remaining elements with full_width stacking logic
                        remaining_elements = selected_elements[elem_idx:]
                        for remaining_idx, remaining_elem in enumerate(remaining_elements):
                            elem_type = remaining_elem.get("element_type", "")
                            elem_label = remaining_elem.get("label") or remaining_elem.get("config", {}).get("chart_name") or f"Element {elem_idx+remaining_idx}"
                            
                            if "config" not in remaining_elem:
                                remaining_elem["config"] = {}
                            
                            # Check if this is the first element of the section
                            is_first_elem = (remaining_elem is first_element)
                            
                            # Calculate element height
                            elem_height = _calculate_element_height_for_layout(
                                remaining_elem, "full_width", layout, False,
                                is_first_element_of_section=is_first_elem
                            )
                            
                            # Add spacing between elements
                            gutter = max(layout.constraints.gutter_vertical, 0.1)
                            spacing = gutter if elements_on_current_slide > 0 else 0.0
                            total_height_needed = cumulative_height + spacing + elem_height
                            
                            # Use same comprehensive logic as main full_width handler
                            element_dims = get_element_dimensions()
                            available_height = layout.content_height
                            remaining_space = available_height - cumulative_height - spacing
                            
                            # Calculate min_reasonable_height (same as main handler)
                            min_reasonable_height = elem_height * 0.5
                            
                            # For tables, enforce stricter minimum based on row count
                            if elem_type == "table":
                                table_data = remaining_elem.get("config", {}).get("table_data", [])
                                if table_data:
                                    min_rows = min(len(table_data) + 1, element_dims.table_min_rows_before_overflow)
                                    min_table_height = min_rows * element_dims.table_min_row_height * 1.3 + 0.5
                                    min_reasonable_height = max(min_reasonable_height, min_table_height)
                            
                            fits_with_tolerance = total_height_needed <= available_height
                            has_reasonable_space = remaining_space >= min(elem_height, min_reasonable_height)
                            allow_overflow = element_dims.allow_full_width_overflow
                            
                            print(f"      [DEBUG DECISION TRANSITION] {elem_label}: fits={fits_with_tolerance}, allow_overflow={allow_overflow}, has_reasonable={has_reasonable_space}, remaining={remaining_space:.2f}, min_reasonable={min_reasonable_height:.2f}, total_needed={total_height_needed:.2f}, available={available_height:.2f}")
                            
                            if fits_with_tolerance and has_reasonable_space:
                                # Element fits on current slide with reasonable space
                                remaining_elem["config"]["slide_number"] = current_slide
                                remaining_elem["config"]["layout"] = "full_width"
                                elements_on_current_slide += 1
                                cumulative_height = total_height_needed
                                print(f"      [{current_slide}] {elem_type} '{elem_label}' (FULL WIDTH - fits, height: {elem_height:.2f}\", total: {cumulative_height:.2f}\")")
                            elif allow_overflow and has_reasonable_space:
                                # Element doesn't fit but there's reasonable space for partial render
                                remaining_elem["config"]["slide_number"] = current_slide
                                remaining_elem["config"]["layout"] = "full_width"
                                remaining_elem["config"]["_needs_split"] = True
                                remaining_elem["config"]["_available_height"] = remaining_space
                                elements_on_current_slide += 1
                                cumulative_height = available_height
                                print(f"      [{current_slide}] {elem_type} '{elem_label}' (FULL WIDTH - SPLIT, needs: {elem_height:.2f}\", available: {remaining_space:.2f}\")")
                            else:
                                # Element doesn't fit AND not enough space for split, move to next slide
                                current_slide += 1
                                current_slide_layout = "full_width"
                                elements_on_current_slide = 1
                                remaining_elem["config"]["slide_number"] = current_slide
                                remaining_elem["config"]["layout"] = "full_width"
                                
                                # Check if element needs split on new slide
                                new_slide_available = layout.content_height
                                if elem_height > new_slide_available:
                                    remaining_elem["config"]["_needs_split"] = True
                                    remaining_elem["config"]["_available_height"] = new_slide_available
                                    cumulative_height = new_slide_available
                                    print(f"      [{current_slide}] {elem_type} '{elem_label}' (FULL WIDTH - OVERFLOW TO NEXT SLIDE, needs: {elem_height:.2f}\", available: {new_slide_available:.2f}\")")
                                else:
                                    cumulative_height = elem_height
                                    print(f"      [{current_slide}] {elem_type} '{elem_label}' (FULL WIDTH - new slide, height: {elem_height:.2f}\")")
                        
                        # All remaining elements processed, break out of grid loop
                        break
                
                # Set layout for this slide if not already set
                if current_slide_layout is None:
                    current_slide_layout = forced_layout_type if forced_layout_type else "grid_2x2"
                
                element["config"]["slide_number"] = current_slide
                # Use pre-calculated preferred layout for tables, otherwise use forced_layout_type or grid_2x2
                if element_type == "table" and element.get("config", {}).get("_preferred_layout"):
                    element["config"]["layout"] = element["config"]["_preferred_layout"]
                else:
                    element["config"]["layout"] = forced_layout_type if forced_layout_type else "grid_2x2"
                
                # Check minimum dimensions compliance for new slide
                assigned_layout = element["config"]["layout"]
                grid_compliant = _validate_element_minimum_dimensions(element, layout, assigned_layout) if uses_grid else True
                compliance_note = "" if grid_compliant else " [⚠️ min dims]"
                
                print(f"      [{current_slide}] {element_type} '{element_label}' ({assigned_layout.upper()} - slot 1/{slide_capacity}){compliance_note}")
        
        # Apply layout to remaining elements on current slide
        if elements_on_current_slide_list:
            _apply_layout_to_slide_elements(elements_on_current_slide_list, layout, current_slide_num, is_first_slide, forced_layout_type)
            # Calculate final grid height for remaining elements
            cumulative_height = _calculate_grid_elements_height(elements_on_current_slide_list, layout, is_first_slide)
    else:
        # No layout determined and not using grid - this shouldn't happen, but handle gracefully
        print(f"   ⚠️  Warning: No layout determined and not using grid for section")
        # Fallback to full_width
        for elem_idx, element in enumerate(selected_elements):
            element_type = element.get("element_type", "")
            element_label = element.get("label") or element.get("config", {}).get("chart_name") or f"Element {elem_idx}"
            
            if "config" not in element:
                element["config"] = {}
            
            element["config"]["slide_number"] = current_slide
            element["config"]["layout"] = "full_width"
            elements_on_current_slide += 1
            elements_on_current_slide_list.append(element)
            print(f"      [{current_slide}] {element_type} '{element_label}' (FALLBACK - full_width)")
        
        if elements_on_current_slide_list:
            _apply_layout_to_slide_elements(elements_on_current_slide_list, layout, current_slide_num, is_first_slide, "full_width")
    
    # DON'T move to next slide - let sections share slides if there's capacity
    return current_slide, elements_on_current_slide, is_first_slide, cumulative_height, current_slide_layout


def _apply_layout_to_slide_elements(
    elements: list[Dict[str, Any]],
    layout: SlideLayoutMetrics,
    slide_num: int,
    is_first_slide: bool = False,
    forced_layout_type: Optional[str] = None,
) -> None:
    """
    Apply layout to all elements on a slide.
    
    Rules (only apply when layout_preference is not provided and slide is not first):
    - For figures:
      - If all elements are tables → use full_width
      - If there's only one element → use full_width
      - Otherwise → use grid_2x2
    - For snapshot or submarket: always use full_width
    
    Args:
        elements: List of element dictionaries
        layout: SlideLayoutMetrics
        slide_num: Slide number
        is_first_slide: Whether this is the first slide
        forced_layout_type: Optional forced layout type from layout_preference
    """
    if not elements:
        return
    
    # If forced_layout_type is set (layout_preference provided), use it for all elements
    if forced_layout_type:
        for elem in elements:
            elem.setdefault("config", {})["layout"] = forced_layout_type
        return
    
    # Skip new rules for first slide - use existing logic
    if is_first_slide:
        if layout.property_sub_type == "submarket":
            # First slide uses grid (2x3)
            for elem in elements:
                elem.setdefault("config", {})["layout"] = "grid"
        else:
            # For other types, use existing first slide logic
            # Check if any element has explicit full_width layout
            has_explicit_full_width = any(
                elem.get("config", {}).get("layout") == "full_width"
                for elem in elements
            )
            if has_explicit_full_width:
                for elem in elements:
                    elem.setdefault("config", {})["layout"] = "full_width"
            elif layout.property_sub_type == "figures":
                # Figures first slide: use grid_2x2
                for elem in elements:
                    elem.setdefault("config", {})["layout"] = "grid_2x2"
            else:
                # Other types: default to full_width
                for elem in elements:
                    elem.setdefault("config", {})["layout"] = "full_width"
        return
    
    # Apply new rules for non-first slides without layout_preference
    if layout.property_sub_type == "figures":
        # Check if all elements are tables
        all_tables = all(
            elem.get("element_type") == "table"
            for elem in elements
        )
        
        # Check if there's only one element
        single_element = len(elements) == 1
        
        if all_tables or single_element:
            # All tables or single element: use preferred layout if available, otherwise full_width
            for elem in elements:
                if elem.get("element_type") == "table" and elem.get("config", {}).get("_preferred_layout"):
                    elem.setdefault("config", {})["layout"] = elem["config"]["_preferred_layout"]
                else:
                    elem.setdefault("config", {})["layout"] = "full_width"
        else:
            # Multiple elements with mixed types: use preferred layout for tables, grid_2x2 for others
            for elem in elements:
                if elem.get("element_type") == "table" and elem.get("config", {}).get("_preferred_layout"):
                    elem.setdefault("config", {})["layout"] = elem["config"]["_preferred_layout"]
                else:
                    elem.setdefault("config", {})["layout"] = "grid_2x2"
    elif layout.property_sub_type in ("snapshot", "submarket"):
        # Snapshot and submarket: always use full_width for non-first slides
        for elem in elements:
            elem.setdefault("config", {})["layout"] = "full_width"
    else:
        # Other types: default to full_width
        for elem in elements:
            elem.setdefault("config", {})["layout"] = "full_width"


# ============================================================================
# TABLE HEIGHT CALCULATION WITH TEXT WRAPPING
# ============================================================================

def _calculate_table_dimensions_from_data(
    data: List[Dict[str, Any]],
    has_header: bool = True,
    fallback_rows: int = 5,
    fallback_cols: int = 5
) -> Tuple[int, int]:
    """
    Calculate actual table dimensions from data.
    Reuses logic from TableBlock._calculate_actual_dimensions().
    
    Args:
        data: List of data dictionaries
        has_header: Whether table has header row
        fallback_rows: Fallback row count if no data
        fallback_cols: Fallback column count if no data
        
    Returns:
        Tuple of (actual_rows, actual_columns)
    """
    if not data or len(data) == 0:
        return (fallback_rows, fallback_cols)
    
    # Calculate actual rows: data rows + header row
    actual_rows = len(data) + (1 if has_header else 0)
    
    # Calculate actual columns from first data row keys
    if isinstance(data[0], dict):
        actual_columns = len(data[0].keys())
    else:
        actual_columns = fallback_cols
    
    return (actual_rows, actual_columns)


# DEPRECATED: _calculate_table_height_with_wrapping has been removed.
# Use calculate_table_content_height from content_height_calculator.py instead.
# That function properly accounts for text wrapping based on actual cell content.


def _get_element_width_for_layout(
    layout_type: str,
    layout: SlideLayoutMetrics,
    is_first_slide: bool = False
) -> float:
    """
    Get the maximum element width for a given layout type.
    Reuses existing layout properties and calculations.
    
    Args:
        layout_type: Layout type (grid_2x2, full_width, base_slide, hybrid_grid)
        layout: SlideLayoutMetrics with layout information
        is_first_slide: Whether this is the first slide
        
    Returns:
        Maximum element width in inches
    """
    # For first slide, use first slide margins to calculate correct width
    if is_first_slide and layout.layout_config.first_slide_margin_left is not None:
        first_slide_constraints = layout.layout_config.get_constraints(is_first_slide=True)
        first_slide_content_width = first_slide_constraints.content_width
        
        if layout_type == "grid_2x2":
            # For grid on first slide, use quadrant of first slide content width
            # Calculate quadrant width with first slide constraints
            gutter_h = first_slide_constraints.gutter_horizontal
            quadrant_w = _calculate_quadrant_dimension(first_slide_content_width, gutter_h, DEFAULT_GRID_COLS)
            return quadrant_w
        elif layout_type in ("full_width", "base_slide"):
            # Use first slide content width for full-width layouts
            return first_slide_content_width
        elif layout_type == "hybrid_grid":
            # For hybrid grid on first slide, use first slide quadrant width
            gutter_h = first_slide_constraints.gutter_horizontal
            quadrant_w = _calculate_quadrant_dimension(first_slide_content_width, gutter_h, DEFAULT_GRID_COLS)
            return quadrant_w
        else:
            # Default to first slide content width
            return first_slide_content_width
    
    # For regular slides, use regular content width from layout
    if layout_type == "grid_2x2":
        # Reuse existing quadrant_width (already accounts for gutters)
        return layout.quadrant_width
    elif layout_type == "full_width":
        # Reuse existing content_width property
        return layout.content_width
    elif layout_type == "base_slide":
        # For base slide, use content width
        return layout.content_width
    elif layout_type == "hybrid_grid":
        # For hybrid grid, use quadrant width (similar to grid_2x2)
        return layout.quadrant_width
    else:
        # Default to content width
        return layout.content_width


def _should_cap_element_height(
    layout_type: str,
    element_dims: Any,
) -> bool:
    """
    Determine if element height should be capped to slide content height.
    
    Grid layouts (fixed dimensions) always cap height to ensure elements fit in cells.
    Full-width layouts can allow overflow to next slide when configured.
    
    Args:
        layout_type: The layout type (grid_2x2, full_width, base_slide, etc.)
        element_dims: ElementDimensions config object with allow_full_width_overflow flag
        
    Returns:
        True if height should be capped, False if intrinsic height should be used
    """
    # Fixed layouts always cap height to cell dimensions
    fixed_layouts = {"grid_2x2", "hybrid_grid"}
    
    if layout_type in fixed_layouts:
        return True
    
    # Full-width and base_slide: check config for overflow behavior
    if layout_type in {"full_width", "base_slide"}:
        # When allow_full_width_overflow is True, don't cap (allow overflow to next slide)
        # When False, cap height to slide content (legacy behavior)
        return not element_dims.allow_full_width_overflow
    
    # Default: cap height for unknown layout types
    return True


def _calculate_element_height_for_layout(
    element: Dict[str, Any],
    layout_type: str,
    layout: SlideLayoutMetrics,
    is_first_slide: bool = False,
    debug_log: bool = False,
    is_first_element_of_section: bool = False
) -> float:
    """
    Calculate accurate element height for a specific layout type.
    Accounts for text wrapping based on actual layout width.
    
    This is the primary function for height calculation that should be used
    throughout the slide assignment process to ensure accurate heights.
    
    Args:
        element: Element dictionary with element_type and config
        layout_type: Layout type (grid_2x2, full_width, base_slide, etc.)
        layout: SlideLayoutMetrics with property_sub_type info
        is_first_slide: Whether this is the first slide
        debug_log: Whether to print detailed debug logging
        is_first_element_of_section: Whether this is the first element in a section
        
    Returns:
        Total height in inches including label and source space
    """
    element_type = element.get("element_type", "")
    config = element.get("config", {})
    element_label = element.get("label") or config.get("chart_name") or config.get("table_label") or "Unnamed"
    
    # Get element dimensions from config
    element_dims = get_element_dimensions()
    
    # Get actual width for this layout type
    available_width = _get_element_width_for_layout(layout_type, layout, is_first_slide)
    
    # Calculate label/source heights (reuse existing helper)
    top_space, bottom_space = _calculate_label_source_height(
        element, element_dims, is_first_element_of_section
    )
    # Calculate element-specific height based on type
    # NOTE: We now calculate content height separately, then add labels via calculate_total_element_height
    if element_type == "table":
        # Get table data (already transformed by frontend_json_processor)
        data = config.get("table_data", [])
        
        # Use content-based calculation for accurate height accounting for text wrapping
        from app.ppt_engine.ppt_helpers_utils.ppt_helpers.content_height_calculator import (
            calculate_table_content_height,
            calculate_total_element_height
        )
        
        # Check if table has source (source row is added INSIDE the table)
        has_table_source = bool(config.get("table_source"))
        
        # NOTE: Data is already transformed by frontend_json_processor before this stage.
        # All stages (assignment, orchestration, rendering) use the same transformed data.
        table_content_height, _, _ = calculate_table_content_height(
            data=data,
            table_width=available_width,
            element_dims=element_dims,
            has_header=True,
            has_source=has_table_source
        )
        
        # Calculate total height including labels and content (NOT section title)
        # Section title space is added separately by the orchestrator based on display_order
        # This ensures consistent height calculation across assignment and rendering
        total_height = calculate_total_element_height(
            content_height=table_content_height,
            element=element,
            is_first_in_section=False,  # Never include section title here - orchestrator handles it
            section_style=None,
            element_dims=element_dims
        )
        
        # Add section title space for first element (matching orchestrator's logic)
        if is_first_element_of_section:
            total_height += element_dims.get_section_title_total_height()
        
    elif element_type == "chart":
        # Use content-based calculation for accurate chart height
        from app.ppt_engine.ppt_helpers_utils.ppt_helpers.content_height_calculator import (
            calculate_chart_content_height,
            calculate_total_element_height
        )
        
        chart_data = config.get("chart_data", [])
        chart_type = config.get("chart_type")
        
        chart_content_height = calculate_chart_content_height(
            chart_data=chart_data,
            chart_width=available_width,
            element_dims=element_dims,
            chart_type=chart_type
        )
        
        # Apply dynamic layout ratios from config
        min_height = available_width * element_dims.dynamic_layout_min_height_ratio
        max_height = available_width * element_dims.dynamic_layout_max_height_ratio
        chart_content_height = max(min_height, min(chart_content_height, max_height))
        
        # Calculate total height including all components (section title, labels, content, source)
        total_height = calculate_total_element_height(
            content_height=chart_content_height,
            element=element,
            is_first_in_section=is_first_element_of_section,
            section_style=None,  # Will be passed from caller if needed
            element_dims=element_dims
        )
        
    elif element_type == "commentary":
        # Commentary uses dynamic layout ratios from config
        text = (
            config.get("commentary_json")
            or config.get("commentary_text")
            or config.get("content", "")
        )
        text_length = len(text) if text else 0
        
        # Calculate lines based on available width
        chars_per_line = int(available_width * element_dims.commentary_chars_per_line / layout.content_width)
        chars_per_line = max(chars_per_line, 40)  # Minimum reasonable chars per line
        line_height = element_dims.commentary_line_height
        
        # Estimate lines
        lines = max(1, text_length // chars_per_line)
        content_height = lines * line_height
        
        # Apply dynamic layout ratios from config
        min_height = available_width * element_dims.dynamic_layout_min_height_ratio
        max_height = available_width * element_dims.dynamic_layout_max_height_ratio
        content_height = max(min_height, min(content_height, max_height))
        
        # Calculate total height including all components
        from app.ppt_engine.ppt_helpers_utils.ppt_helpers.content_height_calculator import calculate_total_element_height
        
        total_height = calculate_total_element_height(
            content_height=content_height,
            element=element,
            is_first_in_section=is_first_element_of_section,
            section_style=None,
            element_dims=element_dims
        )
        
    else:
        # Default size for unknown types - use dynamic layout min from config
        min_height = available_width * element_dims.dynamic_layout_min_height_ratio
        
        # Calculate total height including all components
        from app.ppt_engine.ppt_helpers_utils.ppt_helpers.content_height_calculator import calculate_total_element_height
        
        total_height = calculate_total_element_height(
            content_height=min_height,
            element=element,
            is_first_in_section=is_first_element_of_section,
            section_style=None,
            element_dims=element_dims
        )
    
    # Height capping logic depends on layout type:
    # - Grid layouts (grid_2x2): Always cap to cell/content height (fixed dimensions)
    # - Full-width layouts: Allow overflow to next slide when allow_full_width_overflow is True
    should_cap_height = _should_cap_element_height(layout_type, element_dims)
    
    if should_cap_height:
        # Fixed layouts: cap height to available slide content height
        total_height = min(total_height, layout.content_height)
    # else: Full-width with overflow enabled - use true intrinsic height (no capping)
    
    total_height = max(total_height, element_dims.table_min_row_height * 3)  # Absolute minimum
    
    # Debug logging if requested
    if debug_log:
        print(f"         💡 Height calculation for {element_type} '{element_label}':")
        print(f"            Layout: {layout_type}, Width: {available_width:.2f}\"")
        print(f"            Total height: {total_height:.2f}\"")
    
    return total_height


def _calculate_label_source_height(
    element: Dict[str, Any],
    element_dims: Any,
    is_first_element_of_section: bool = False
) -> Tuple[float, float]:
    """
    Calculate label and source heights for an element.
    Extracted from _estimate_element_size() to avoid duplication.
    
    Args:
        element: Element dictionary
        element_dims: ElementDimensions config object
        is_first_element_of_section: Whether this is the first element in a section
        
    Returns:
        Tuple of (top_space, bottom_space) in inches
    """
    config = element.get("config", {})
    element_type = element.get("element_type", "")
    
    # Calculate label space
    top_space = 0.0
    
    # Add section title space if this is the first element of a section
    # Uses get_section_title_total_height() for consistent spacing (single source of truth)
    if is_first_element_of_section:
        top_space += element_dims.get_section_title_total_height()
    
    # Check if element has heading/label
    has_heading = bool(
        element.get("label") or 
        config.get("label") or 
        config.get("table_label") or
        config.get("chart_label")
    )
    
    if has_heading:
        top_space += element_dims.get_figure_label_total_height()
    
    # Check if element has source
    has_source = bool(
        config.get("table_source") or
        config.get("source")
    )
    
    bottom_space = 0.0
    # For tables, source is now a row INSIDE the table (0.23" included in table height)
    # So we don't add external source space for tables
    # For charts and other elements, source is external, so add source_gap + source_label_height
    if has_source and element_type != "table":
        bottom_space += element_dims.source_gap + element_dims.source_label_height
    
    return (top_space, bottom_space)


def _evaluate_table_layouts(
    element: Dict[str, Any],
    layout: SlideLayoutMetrics,
    allowed_layouts: Set[str],
    is_first_slide: bool = False
) -> Optional[Tuple[str, float, float]]:
    """
    Evaluate all possible layouts for a table and select the best one.
    Reuses existing estimation and label/source height calculation logic.
    
    Args:
        element: Table element dictionary
        layout: SlideLayoutMetrics with layout information
        allowed_layouts: Set of allowed layout types for this section
        is_first_slide: Whether this is the first slide
        
    Returns:
        Tuple of (best_layout_type, width, total_height) or None if no valid layout
    """
    element_dims = get_element_dimensions()
    config = element.get("config", {})
    data = config.get("table_data", [])
    
    # Get table dimensions
    if data and len(data) > 0:
        rows = len(data) + 1  # +1 for header
        if isinstance(data[0], dict):
            cols = len(data[0].keys())
        else:
            cols = len(data[0]) if hasattr(data[0], '__len__') else config.get("columns", 5)
    else:
        rows = config.get("rows", 5)
        cols = config.get("columns", 5)
    
    # Evaluate each allowed layout
    from app.ppt_engine.ppt_helpers_utils.ppt_helpers.content_height_calculator import (
        calculate_table_content_height,
        calculate_total_element_height
    )
    
    # Determine if this is the first element of a section (needed for calculate_total_element_height)
    # This is a table evaluation function, so we'll assume it's not the first element
    # (the caller should handle first element logic separately)
    is_first_element_of_section = False
    
    layout_options = []
    for layout_type in allowed_layouts:
        # Get element width for this layout
        element_width = _get_element_width_for_layout(layout_type, layout, is_first_slide)
        
        # Check if table has source (source row is added INSIDE the table)
        has_table_source = bool(config.get("table_source"))
        
        # Calculate table content height using content-based calculation
        table_content_height, _, _ = calculate_table_content_height(
            data=data,
            table_width=element_width,
            element_dims=element_dims,
            has_header=True,
            has_source=has_table_source
        )
        
        # Use calculate_total_element_height to get total height including all components
        # This ensures source height is correctly included (0.23" for tables, inside the table)
        # and matches the logic used in _calculate_element_height_for_layout
        total_height = calculate_total_element_height(
            content_height=table_content_height,
            element=element,
            is_first_in_section=is_first_element_of_section,
            section_style=None,
            element_dims=element_dims
        )
        
        # Check if it fits in available space
        fits = total_height <= layout.content_height
        
        layout_options.append((layout_type, element_width, total_height, fits))
    
    if not layout_options:
        return None
    
    # Select best layout: prefer fits, then smallest height, then widest
    # Sort by: fits (desc), height (asc), width (desc)
    layout_options.sort(key=lambda x: (-x[3], x[2], -x[1]))
    
    best_layout = layout_options[0]
    return (best_layout[0], best_layout[1], best_layout[2])


# ============================================================================
# SIZE ESTIMATION & FIT CHECKING
# ============================================================================

def _estimate_element_size(
    element: Dict[str, Any],
    layout: SlideLayoutMetrics,
    full_width: bool = False,
) -> Tuple[float, float]:
    """
    Estimate the intrinsic size (width, height) of an element in inches.
    
    Args:
        element: Element dictionary with element_type and config
        layout: SlideLayoutMetrics with property_sub_type info
        full_width: If True, element uses full content width (for full_width layout)
        
    Returns:
        (width, height) tuple in inches
    """
    element_type = element.get("element_type", "")
    config = element.get("config", {})
    
    # Get element dimensions from config
    element_dims = get_element_dimensions()
    
    # For full_width layout, always use full content width
    available_width = layout.content_width if full_width else layout.quadrant_width
    
    # Calculate minimum dimensions based on layout type and config
    table_min_width = layout.content_width * element_dims.table_min_width_ratio
    table_min_height = element_dims.table_min_row_height

    if element_type == "commentary":
        # Commentary uses dynamic layout ratios from config
        text = (
            config.get("commentary_json")
            or config.get("commentary_text")
            or config.get("content", "")
        )
        text_length = len(text) if text else 0
        
        # Use element dimensions for commentary estimation
        chars_per_line = element_dims.commentary_chars_per_line
        line_height = element_dims.commentary_line_height
        
        # Estimate lines based on text length
        lines = max(1, text_length // chars_per_line)
        height_estimate = lines * line_height
        
        # Apply dynamic layout ratios from config
        min_height = available_width * element_dims.dynamic_layout_min_height_ratio
        max_height = available_width * element_dims.dynamic_layout_max_height_ratio
        height = max(min_height, min(height_estimate, max_height, layout.content_height))
        width = available_width
        
        return (width, height)
    
    elif element_type == "chart":
        # Charts use dynamic layout ratios from config
        width = available_width
        
        # Calculate height from aspect ratio
        aspect_ratio = 1.6  # Default aspect ratio for charts
        base_height = width / aspect_ratio
        
        # Estimate legend height based on actual chart data if available
        chart_data = config.get("chart_data", [])
        if chart_data and len(chart_data) > 0:
            # Analyze data structure to count series
            if isinstance(chart_data[0], dict):
                columns = list(chart_data[0].keys())
                series_count = len(columns) - 1 if len(columns) > 1 else 1
            else:
                series_count = 1
            
            # Estimate legend height based on series count
            if series_count <= 2:
                legend_height = 0.15
            elif series_count <= 4:
                legend_height = 0.20
            else:
                legend_height = 0.25
        else:
            legend_height = 0.15  # Default legend height
        
        content_height = base_height + legend_height
        
        # Apply dynamic layout ratios from config
        min_height = width * element_dims.dynamic_layout_min_height_ratio
        max_height = width * element_dims.dynamic_layout_max_height_ratio
        content_height = max(min_height, min(content_height, max_height))
        
        # Always reserve space for labels within cell (show/hide based on config)
        # This ensures consistent cell heights and prevents overlaps
        figure_label_space = element_dims.get_figure_label_total_height()
        source_label_space = element_dims.source_gap + element_dims.source_label_height
        total_label_space = figure_label_space + source_label_space
        height = content_height + total_label_space
        
        # Ensure width doesn't exceed available space
        width = min(width, layout.content_width)
        
        return (width, height)
    
    elif element_type == "table":
        # Tables depend on rows and columns - use actual data when available
        data = config.get("table_data", [])
        
        if data and len(data) > 0:
            # Use actual data dimensions
            rows = len(data) + 1  # +1 for header
            if isinstance(data[0], dict):
                cols = len(data[0].keys())
            else:
                cols = len(data[0]) if hasattr(data[0], '__len__') else config.get("columns", 5)
        else:
            # Fall back to config estimates
            rows = config.get("rows", 5)
            cols = config.get("columns", 5)
        
        # Calculate width: columns * min_col_width * safety_margin + padding
        if full_width:
            width_estimate = layout.content_width
        else:
            min_col_width = element_dims.table_min_col_width
            cell_padding = element_dims.table_cell_padding
            height_safety_margin = element_dims.table_height_safety_margin
            width_estimate = cols * min_col_width * height_safety_margin + (cols + 1) * cell_padding
        
        # Enforce minimum width and ensure it doesn't exceed content width
        width = max(min(width_estimate, layout.content_width), table_min_width)
        
        # Calculate height using content-based calculation
        from app.ppt_engine.ppt_helpers_utils.ppt_helpers.content_height_calculator import (
            calculate_table_content_height,
            calculate_total_element_height
        )
        
        # For tables, check if we have a preferred layout with pre-calculated width
        preferred_layout = element.get("config", {}).get("_preferred_layout")
        if preferred_layout:
            # Use the width from the preferred layout evaluation
            preferred_width = _get_element_width_for_layout(preferred_layout, layout, False)
            table_width_to_use = preferred_width if preferred_width > 0 else width
        else:
            table_width_to_use = width
        
        # Check if table has source (source row is added INSIDE the table)
        has_table_source = bool(config.get("table_source"))
        
        # Use content-based calculation (accounts for text wrapping)
        table_content_height, _, _ = calculate_table_content_height(
            data=data,
            table_width=table_width_to_use,
            element_dims=element_dims,
            has_header=True,
            has_source=has_table_source
        )
        
        # Calculate total height including all components (section title, labels, content, source)
        # Note: is_first_in_section is False here as we don't have section context in sizing estimation
        height_estimate = calculate_total_element_height(
            content_height=table_content_height,
            element=element,
            is_first_in_section=False,
            section_style=None,
            element_dims=element_dims
        )
        
        # Enforce minimum height while respecting content boundaries
        height = max(min(height_estimate, layout.content_height), table_min_height)
        
        return (width, height)
    
    else:
        # Default size for unknown types - use dynamic layout ratios from config
        width = available_width
        
        # Use dynamic layout min ratio for height
        min_height = width * element_dims.dynamic_layout_min_height_ratio
        height = max(layout.quadrant_height, min_height)
        
        # Ensure width doesn't exceed content boundaries
        width = min(width, layout.content_width)
        
        return (width, height)


def _can_fit_in_quadrant(element: Dict[str, Any], layout: SlideLayoutMetrics) -> bool:
    """
    Check if an element can fit in a single quadrant (1/4 of slide).
    
    Grid logic only applies if property_sub_type is figures or submarket.
    Ensures minimum dimensions are respected in all layout decisions.
    
    Args:
        element: Element dictionary
        layout: SlideLayoutMetrics with property_sub_type info
        
    Returns:
        True if element fits in quadrant, False if needs more space
    """
    # Grid only applies if property_sub_type is figures or submarket
    uses_grid = layout.property_sub_type in ("figures", "submarket")
    
    if not uses_grid:
        # For non-grid types, elements always fit (they use full slide)
        return True
    
    element_type = element.get("element_type", "")
    width, height = _estimate_element_size(element, layout, full_width=False)
    
    # Check against quadrant dimensions with tolerance from config
    element_dims = get_element_dimensions()
    fits_width = width <= layout.quadrant_width * element_dims.quadrant_fit_tolerance
    fits_height = height <= layout.quadrant_height * element_dims.quadrant_fit_tolerance
    
    # Special cases
    if element_type == "commentary":
        # Commentary can overflow vertically, so we're more lenient on height
        # As long as width fits, it's okay
        return fits_width
    
    elif element_type == "table":
        # Tables can overflow horizontally
        # Check if height fits, be lenient on width
        if height > layout.quadrant_height * 1.5:
            # Table is too tall even with overflow
            return False
        return True  # Width can overflow
    
    elif element_type == "chart":
        # Charts need both dimensions to fit for proper rendering
        return fits_width and fits_height
    
    else:
        # Other element types must fit in quadrant
        return fits_width and fits_height


# ============================================================================
# MINIMUM DIMENSION VALIDATION
# ============================================================================

def _validate_element_minimum_dimensions(
    element: Dict[str, Any], 
    layout: SlideLayoutMetrics,
    assigned_layout_type: str = "grid_2x2"
) -> bool:
    """
    Validate that an element meets minimum dimension requirements for its type.
    
    Args:
        element: Element dictionary with element_type and config
        layout: SlideLayoutMetrics with property_sub_type info
        assigned_layout_type: The layout type assigned to this element
        
    Returns:
        True if element meets minimum requirements, False otherwise
    """
    element_type = element.get("element_type", "")
    
    # Determine if element will use full width
    uses_full_width = assigned_layout_type in ("full_width", "base_slide")
    
    # Get actual dimensions for this element
    width, height = _estimate_element_size(element, layout, full_width=uses_full_width)
    
    # Get element dimensions from config
    element_dims = get_element_dimensions()
    
    # Calculate minimum dimensions for readable elements
    # Use fixed absolute minimums rather than scaling, as charts fill available space
    # Note: available_width/height used for context, minimums are fixed for readability
    _ = layout.content_width if uses_full_width else layout.quadrant_width  # available_width (unused)
    _ = layout.content_height if uses_full_width else layout.quadrant_height  # available_height (unused)
    
    if element_type == "table":
        # Tables need minimum column width * some columns
        min_width = element_dims.table_min_col_width * 5  # 5 columns minimum
        min_height = element_dims.table_min_row_height * 3  # At least header + 2 rows
    elif element_type == "chart":
        # Charts need enough space to be readable
        # Use a fixed minimum (2" width, 1.5" height) that represents readable chart size
        min_width = 2.0  # Minimum readable chart width
        min_height = 1.5  # Minimum readable chart height
    else:
        # Commentary and other elements
        min_width = 2.0
        min_height = 1.0
    
    # Check if dimensions meet minimums (with tolerance from config)
    element_dims = get_element_dimensions()
    meets_width = width >= min_width * element_dims.minimum_dimension_tolerance
    meets_height = height >= min_height * element_dims.minimum_dimension_tolerance
    
    if not meets_width or not meets_height:
        print(f"      ⚠️  Dimension warning for {element_type}: "
              f"size {width:.2f}x{height:.2f} vs min {min_width:.2f}x{min_height:.2f}")
        return False
    
    return True


def _ensure_minimum_dimensions_compliance(json_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-process assigned elements to ensure all meet minimum dimension requirements.
    Adjusts layout assignments if needed to maintain compliance.
    
    Args:
        json_data: JSON data with assigned slide numbers and layouts
        
    Returns:
        Modified JSON with layout adjustments for minimum dimension compliance
    """
    sections = json_data.get("sections", [])
    layout = _build_layout_metrics(json_data)
    
    print(f"\n{'='*60}")
    print(f"🔍 MINIMUM DIMENSIONS VALIDATION")
    print(f"{'='*60}")
    
    violations_found = 0
    adjustments_made = 0
    
    for section in sections:
        if not section.get("selected", True):
            continue
            
        section_name = section.get("name", section.get("key", "Unknown"))
        
        for element in section.get("elements", []):
            if not element.get("selected", True):
                continue
                
            config = element.setdefault("config", {})
            element_type = element.get("element_type", "")
            element_label = element.get("label") or f"Element {element.get('id', '?')}"
            assigned_layout = config.get("layout", "grid_2x2")
            
            # Validate current assignment
            is_compliant = _validate_element_minimum_dimensions(element, layout, assigned_layout)
            
            if not is_compliant:
                violations_found += 1
                
                # Try to fix by switching to full_width layout
                if assigned_layout != "full_width":
                    print(f"   🔧 Adjusting {section_name}/{element_label} to full_width layout")
                    config["layout"] = "full_width"
                    
                    # Re-validate with new layout
                    is_compliant_after = _validate_element_minimum_dimensions(element, layout, "full_width")
                    
                    if is_compliant_after:
                        adjustments_made += 1
                        print(f"      ✅ Dimension compliance restored")
                    else:
                        print(f"      ⚠️  Still non-compliant after adjustment")
                else:
                    print(f"   ⚠️  {section_name}/{element_label} cannot be made compliant")
            else:
                print(f"   ✅ {section_name}/{element_label} ({assigned_layout}): Compliant")
    
    print(f"\n📊 Validation Summary:")
    print(f"   Violations found: {violations_found}")
    print(f"   Adjustments made: {adjustments_made}")
    print(f"{'='*60}\n")
    
    return json_data


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_slide_statistics(json_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get statistics about slide assignments in the data.
    
    Args:
        json_data: JSON data with assigned slide numbers
        
    Returns:
        Dictionary with statistics
    """
    sections = json_data.get("sections", [])
    
    slide_numbers = set()
    element_count = 0
    elements_by_slide = {}
    
    for section in sections:
        for element in section.get("elements", []):
            if element.get("selected", True):
                element_count += 1
                slide_num = element.get("config", {}).get("slide_number")
                if slide_num:
                    slide_numbers.add(slide_num)
                    if slide_num not in elements_by_slide:
                        elements_by_slide[slide_num] = []
                    elements_by_slide[slide_num].append(element)
    
    return {
        "total_slides": len(slide_numbers),
        "total_elements": element_count,
        "elements_by_slide": elements_by_slide,
        "slide_numbers": sorted(slide_numbers)
    }


def print_slide_assignments(json_data: Dict[str, Any]) -> None:
    """
    Print a summary of slide assignments for debugging.
    
    Args:
        json_data: JSON data with assigned slide numbers
    """
    stats = get_slide_statistics(json_data)
    
    print(f"\n{'='*60}")
    print(f"📊 SLIDE ASSIGNMENT SUMMARY")
    print(f"{'='*60}")
    print(f"Total slides: {stats['total_slides']}")
    print(f"Total elements: {stats['total_elements']}")
    print()
    
    for slide_num in stats['slide_numbers']:
        elements = stats['elements_by_slide'][slide_num]
        print(f"Slide {slide_num}: {len(elements)} elements")
        for elem in elements:
            elem_type = elem.get("element_type", "unknown")
            label = elem.get("label") or elem.get("config", {}).get("chart_name") or "Unnamed"
            print(f"  - {elem_type}: {label}")
    
    print(f"{'='*60}\n")

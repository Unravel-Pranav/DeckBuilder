#!/usr/bin/env python3
"""
Slide Organizer - Physical layout organization for PPT slides

This module organizes elements into physical slide layouts based on assigned slide numbers.
Creates 2x2 grid layouts with precise positioning for each quadrant.

Author: AI Assistant
Date: 2025-10-17
"""

from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict


# ============================================================================
# LAYOUT CONFIGURATION
# ============================================================================

# Slide dimensions (in inches)
SLIDE_WIDTH = 10.0
SLIDE_HEIGHT = 7.5

# Content area margins
CONTENT_TOP_MARGIN = 1.0  # Below header
CONTENT_BOTTOM_MARGIN = 0.4
CONTENT_LEFT_MARGIN = 0.2
CONTENT_RIGHT_MARGIN = 0.1

# Available content area
CONTENT_WIDTH = SLIDE_WIDTH - CONTENT_LEFT_MARGIN - CONTENT_RIGHT_MARGIN
CONTENT_HEIGHT = SLIDE_HEIGHT - CONTENT_TOP_MARGIN - CONTENT_BOTTOM_MARGIN

# Grid spacing
GRID_GUTTER_HORIZONTAL = 1.0  # Space between columns
GRID_GUTTER_VERTICAL = 0.4  # Space between rows


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Position:
    """Physical position and size for an element on a slide."""
    left: float  # inches from left edge
    top: float  # inches from top edge
    width: float  # inches
    height: float  # inches
    quadrant: int  # Which quadrant (0-3 for 2x2 grid)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class SlideLayout:
    """Complete layout specification for a single slide."""
    slide_number: int
    layout_type: str  # "base_with_kpis", "grid_2x2", "full_slide"
    elements: List[Dict[str, Any]]  # Elements on this slide
    positions: Dict[str, Position]  # Element ID -> Position mapping
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "slide_number": self.slide_number,
            "layout_type": self.layout_type,
            "elements": self.elements,
            "positions": {k: v.to_dict() for k, v in self.positions.items()}
        }


# ============================================================================
# MAIN ORGANIZATION FUNCTION
# ============================================================================

def organize_slides_by_number(json_data: Dict[str, Any]) -> List[SlideLayout]:
    """
    Organize elements into physical slide layouts based on assigned slide numbers.
    
    Args:
        json_data: JSON data with slide_number assigned to elements
        
    Returns:
        List of SlideLayout objects, one per slide
    """
    sections = json_data.get("sections", [])
    
    # Group elements by slide number
    elements_by_slide: Dict[int, List[Dict[str, Any]]] = {}
    
    for section_idx, section in enumerate(sections):
        if not section.get("selected", True):
            continue
        
        section_name = section.get("name", section.get("key", f"Section {section_idx}"))
        
        for element in section.get("elements", []):
            if not element.get("selected", True):
                continue
            
            slide_num = element.get("config", {}).get("slide_number")
            if slide_num is None:
                continue
            
            # Add section context to element
            element_with_context = {
                **element,
                "_section_name": section_name,
                "_section_index": section_idx
            }
            
            if slide_num not in elements_by_slide:
                elements_by_slide[slide_num] = []
            
            elements_by_slide[slide_num].append(element_with_context)
    
    # Create layouts for each slide
    layouts = []
    
    for slide_num in sorted(elements_by_slide.keys()):
        elements = elements_by_slide[slide_num]
        
        # Determine layout type
        if slide_num == 1:
            layout_type = "base_with_kpis"
        elif len(elements) == 1:
            layout_type = "full_slide"
        else:
            layout_type = "grid_2x2"
        
        # Create layout
        layout = _create_slide_layout(
            slide_number=slide_num,
            elements=elements,
            layout_type=layout_type
        )
        
        layouts.append(layout)
    
    return layouts


def _create_slide_layout(
    slide_number: int,
    elements: List[Dict[str, Any]],
    layout_type: str
) -> SlideLayout:
    """
    Create a complete layout for a single slide.
    
    Args:
        slide_number: Slide number
        elements: Elements on this slide
        layout_type: Layout type
        
    Returns:
        SlideLayout object
    """
    if layout_type == "base_with_kpis":
        positions = _create_first_slide_layout(elements)
    elif layout_type == "full_slide":
        positions = _create_full_slide_layout(elements)
    else:  # grid_2x2
        positions = _create_2x2_grid_layout(elements)
    
    return SlideLayout(
        slide_number=slide_number,
        layout_type=layout_type,
        elements=elements,
        positions=positions
    )


# ============================================================================
# LAYOUT CREATORS
# ============================================================================

def _create_2x2_grid_positions() -> List[Position]:
    """
    Calculate the four quadrant positions for a 2x2 grid.
    
    Returns:
        List of 4 Position objects (top-left, top-right, bottom-left, bottom-right)
    """
    # Calculate quadrant dimensions
    quadrant_width = (CONTENT_WIDTH - GRID_GUTTER_HORIZONTAL) / 2
    quadrant_height = (CONTENT_HEIGHT - GRID_GUTTER_VERTICAL) / 2
    
    # Calculate positions for each quadrant
    positions = [
        # Quadrant 0: Top-left
        Position(
            left=CONTENT_LEFT_MARGIN,
            top=CONTENT_TOP_MARGIN,
            width=quadrant_width,
            height=quadrant_height,
            quadrant=0
        ),
        # Quadrant 1: Top-right
        Position(
            left=CONTENT_LEFT_MARGIN + quadrant_width + GRID_GUTTER_HORIZONTAL,
            top=CONTENT_TOP_MARGIN,
            width=quadrant_width,
            height=quadrant_height,
            quadrant=1
        ),
        # Quadrant 2: Bottom-left
        Position(
            left=CONTENT_LEFT_MARGIN,
            top=CONTENT_TOP_MARGIN + quadrant_height + GRID_GUTTER_VERTICAL,
            width=quadrant_width,
            height=quadrant_height,
            quadrant=2
        ),
        # Quadrant 3: Bottom-right
        Position(
            left=CONTENT_LEFT_MARGIN + quadrant_width + GRID_GUTTER_HORIZONTAL,
            top=CONTENT_TOP_MARGIN + quadrant_height + GRID_GUTTER_VERTICAL,
            width=quadrant_width,
            height=quadrant_height,
            quadrant=3
        ),
    ]
    
    return positions


def _create_2x2_grid_layout(elements: List[Dict[str, Any]]) -> Dict[str, Position]:
    """
    Create 2x2 grid layout for elements.
    
    Args:
        elements: List of elements (up to 4)
        
    Returns:
        Dictionary mapping element IDs to positions
    """
    grid_positions = _create_2x2_grid_positions()
    positions = {}
    
    # Sort elements by display_order to maintain order
    sorted_elements = sorted(elements, key=lambda e: e.get("display_order", 0))
    
    # Assign each element to a quadrant
    for idx, element in enumerate(sorted_elements[:4]):  # Max 4 elements in 2x2 grid
        element_id = str(element.get("id", f"elem_{idx}"))
        positions[element_id] = grid_positions[idx]
    
    return positions


def _create_first_slide_layout(elements: List[Dict[str, Any]]) -> Dict[str, Position]:
    """
    Create layout for first slide (Base with KPIs template).
    
    First slide typically has:
    - KPIs or title at top
    - Commentary in left section
    - Chart/table in right section
    
    Args:
        elements: List of elements (up to 2)
        
    Returns:
        Dictionary mapping element IDs to positions
    """
    positions = {}
    
    # Sort elements by display_order
    sorted_elements = sorted(elements, key=lambda e: e.get("display_order", 0))
    
    if len(sorted_elements) == 0:
        return positions
    
    if len(sorted_elements) == 1:
        # Single element - give it most of the space
        element = sorted_elements[0]
        element_id = str(element.get("id", "elem_0"))
        
        positions[element_id] = Position(
            left=CONTENT_LEFT_MARGIN,
            top=CONTENT_TOP_MARGIN,
            width=CONTENT_WIDTH * 0.95,
            height=CONTENT_HEIGHT * 0.9,
            quadrant=0
        )
    else:
        # Two elements - split horizontally
        # First element (usually commentary) on left
        elem1 = sorted_elements[0]
        elem1_id = str(elem1.get("id", "elem_0"))
        
        # Second element (usually chart) on right
        elem2 = sorted_elements[1]
        elem2_id = str(elem2.get("id", "elem_1"))
        
        split_point = CONTENT_WIDTH * 0.45  # 45% for left, 55% for right
        gutter = 0.5
        
        positions[elem1_id] = Position(
            left=CONTENT_LEFT_MARGIN,
            top=CONTENT_TOP_MARGIN,
            width=split_point,
            height=CONTENT_HEIGHT * 0.9,
            quadrant=0
        )
        
        positions[elem2_id] = Position(
            left=CONTENT_LEFT_MARGIN + split_point + gutter,
            top=CONTENT_TOP_MARGIN,
            width=CONTENT_WIDTH - split_point - gutter,
            height=CONTENT_HEIGHT * 0.9,
            quadrant=1
        )
    
    return positions


def _create_full_slide_layout(elements: List[Dict[str, Any]]) -> Dict[str, Position]:
    """
    Create full-slide layout for a single large element.
    
    Args:
        elements: List with single element
        
    Returns:
        Dictionary mapping element ID to position
    """
    positions = {}
    
    if len(elements) > 0:
        element = elements[0]
        element_id = str(element.get("id", "elem_0"))
        
        positions[element_id] = Position(
            left=CONTENT_LEFT_MARGIN,
            top=CONTENT_TOP_MARGIN,
            width=CONTENT_WIDTH * 0.98,
            height=CONTENT_HEIGHT * 0.95,
            quadrant=0
        )
    
    return positions


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def export_layouts_to_json(layouts: List[SlideLayout], output_path: str = None) -> str:
    """
    Export layouts to JSON format for debugging/inspection.
    
    Args:
        layouts: List of SlideLayout objects
        output_path: Optional output file path
        
    Returns:
        JSON string
    """
    import json
    
    layouts_dict = [layout.to_dict() for layout in layouts]
    json_str = json.dumps(layouts_dict, indent=2)
    
    if output_path:
        with open(output_path, 'w') as f:
            f.write(json_str)
    
    return json_str


def print_layout_summary(layouts: List[SlideLayout]) -> None:
    """
    Print a summary of layouts for debugging.
    
    Args:
        layouts: List of SlideLayout objects
    """
    print(f"\n{'='*60}")
    print(f"📐 SLIDE LAYOUT SUMMARY")
    print(f"{'='*60}")
    print(f"Total slides: {len(layouts)}")
    print()
    
    for layout in layouts:
        print(f"Slide {layout.slide_number}: {layout.layout_type}")
        print(f"  Elements: {len(layout.elements)}")
        
        for elem_id, position in layout.positions.items():
            # Find element
            element = next((e for e in layout.elements if str(e.get("id")) == elem_id), None)
            if element:
                elem_type = element.get("element_type", "unknown")
                label = element.get("label") or element.get("config", {}).get("chart_name") or "Unnamed"
                print(f"    - {elem_type} '{label}'")
                print(f"      Position: ({position.left:.2f}\", {position.top:.2f}\")")
                print(f"      Size: {position.width:.2f}\" × {position.height:.2f}\"")
                print(f"      Quadrant: {position.quadrant}")
        print()
    
    print(f"{'='*60}\n")


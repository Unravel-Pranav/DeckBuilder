#!/usr/bin/env python3
"""
Unit tests for slide_organizer module

Tests physical layout organization for slides:
- 2x2 grid positioning
- First slide layout
- Full slide layout
- Position calculations
"""

import pytest
from hello.utils.slide_organizer import (
    organize_slides_by_number,
    _create_2x2_grid_positions,
    _create_2x2_grid_layout,
    _create_first_slide_layout,
    _create_full_slide_layout,
    Position,
    SlideLayout,
)


# ============================================================================
# TEST FIXTURES
# ============================================================================

def create_test_element(element_id, element_type="commentary", slide_number=1, section_name="Test Section"):
    """Helper to create test elements with slide numbers"""
    return {
        "id": element_id,
        "element_type": element_type,
        "selected": True,
        "display_order": 0,
        "config": {"slide_number": slide_number},
        "label": f"Test {element_type} {element_id}",
        "_section_name": section_name,
        "_section_index": 0
    }


def create_test_json(sections_with_elements):
    """
    Helper to create test JSON structure
    
    Args:
        sections_with_elements: List of tuples (section_name, elements_list)
    """
    sections = []
    for idx, (section_name, elements) in enumerate(sections_with_elements):
        sections.append({
            "name": section_name,
            "display_order": idx,
            "selected": True,
            "elements": elements
        })
    
    return {
        "report": {"name": "Test Report"},
        "sections": sections
    }


# ============================================================================
# GRID POSITION TESTS
# ============================================================================

def test_create_2x2_grid_positions():
    """Test that 2x2 grid creates 4 quadrants"""
    positions = _create_2x2_grid_positions()
    
    assert len(positions) == 4
    
    # Check that all positions are Position objects
    for pos in positions:
        assert isinstance(pos, Position)
        assert pos.left >= 0
        assert pos.top >= 0
        assert pos.width > 0
        assert pos.height > 0
    
    # Check quadrant ordering
    assert positions[0].quadrant == 0  # Top-left
    assert positions[1].quadrant == 1  # Top-right
    assert positions[2].quadrant == 2  # Bottom-left
    assert positions[3].quadrant == 3  # Bottom-right


def test_grid_positions_no_overlap():
    """Test that grid quadrants don't overlap"""
    positions = _create_2x2_grid_positions()
    
    # Top-left and top-right should not overlap
    assert positions[0].left + positions[0].width <= positions[1].left
    
    # Top-left and bottom-left should not overlap
    assert positions[0].top + positions[0].height <= positions[2].top
    
    # Check all combinations
    for i, pos1 in enumerate(positions):
        for j, pos2 in enumerate(positions):
            if i != j:
                # Check if they overlap
                horiz_overlap = not (pos1.left + pos1.width <= pos2.left or 
                                   pos2.left + pos2.width <= pos1.left)
                vert_overlap = not (pos1.top + pos1.height <= pos2.top or 
                                  pos2.top + pos2.height <= pos1.top)
                
                # Should not overlap
                assert not (horiz_overlap and vert_overlap), f"Positions {i} and {j} overlap"


# ============================================================================
# LAYOUT CREATION TESTS
# ============================================================================

def test_create_2x2_grid_layout_one_element():
    """Test 2x2 grid layout with one element"""
    elements = [create_test_element(1)]
    
    positions = _create_2x2_grid_layout(elements)
    
    assert len(positions) == 1
    assert "1" in positions
    assert positions["1"].quadrant == 0  # First quadrant


def test_create_2x2_grid_layout_four_elements():
    """Test 2x2 grid layout with four elements"""
    elements = [
        create_test_element(1),
        create_test_element(2),
        create_test_element(3),
        create_test_element(4)
    ]
    
    positions = _create_2x2_grid_layout(elements)
    
    assert len(positions) == 4
    
    # Check all elements are placed
    for i in range(1, 5):
        assert str(i) in positions
    
    # Check quadrant assignment
    assert positions["1"].quadrant == 0  # Top-left
    assert positions["2"].quadrant == 1  # Top-right
    assert positions["3"].quadrant == 2  # Bottom-left
    assert positions["4"].quadrant == 3  # Bottom-right


def test_create_2x2_grid_layout_respects_display_order():
    """Test that display order affects element placement"""
    elements = [
        {**create_test_element(1), "display_order": 2},
        {**create_test_element(2), "display_order": 0},
        {**create_test_element(3), "display_order": 1}
    ]
    
    positions = _create_2x2_grid_layout(elements)
    
    # Element 2 (display_order 0) should be in first quadrant
    assert positions["2"].quadrant == 0
    # Element 3 (display_order 1) should be in second quadrant
    assert positions["3"].quadrant == 1
    # Element 1 (display_order 2) should be in third quadrant
    assert positions["1"].quadrant == 2


def test_create_first_slide_layout_one_element():
    """Test first slide layout with one element"""
    elements = [create_test_element(1)]
    
    positions = _create_first_slide_layout(elements)
    
    assert len(positions) == 1
    assert "1" in positions
    
    # Should use most of the slide
    pos = positions["1"]
    assert pos.width > 5.0  # Significant width
    assert pos.height > 3.0  # Significant height


def test_create_first_slide_layout_two_elements():
    """Test first slide layout with two elements (typical case)"""
    elements = [
        create_test_element(1, "commentary"),
        create_test_element(2, "chart")
    ]
    
    positions = _create_first_slide_layout(elements)
    
    assert len(positions) == 2
    assert "1" in positions
    assert "2" in positions
    
    # Elements should be side-by-side
    pos1 = positions["1"]
    pos2 = positions["2"]
    
    # Left element should be on the left
    assert pos1.left < pos2.left
    
    # Both should have reasonable dimensions
    assert pos1.width > 2.0
    assert pos2.width > 2.0


def test_create_full_slide_layout():
    """Test full slide layout for single large element"""
    elements = [create_test_element(1, "chart")]
    
    positions = _create_full_slide_layout(elements)
    
    assert len(positions) == 1
    assert "1" in positions
    
    # Should use most of the slide
    pos = positions["1"]
    assert pos.width > 7.0  # Most of slide width
    assert pos.height > 5.0  # Most of slide height


# ============================================================================
# ORGANIZE SLIDES TESTS
# ============================================================================

def test_organize_slides_by_number_single_slide():
    """Test organizing elements into a single slide"""
    elements = [
        create_test_element(1, slide_number=1),
        create_test_element(2, slide_number=1)
    ]
    
    json_data = create_test_json([("Section 1", elements)])
    
    layouts = organize_slides_by_number(json_data)
    
    assert len(layouts) == 1
    assert layouts[0].slide_number == 1
    assert layouts[0].layout_type == "base_with_kpis"  # First slide
    assert len(layouts[0].elements) == 2


def test_organize_slides_by_number_multiple_slides():
    """Test organizing elements into multiple slides"""
    elements = [
        create_test_element(1, slide_number=1),
        create_test_element(2, slide_number=1),
        create_test_element(3, slide_number=2),
        create_test_element(4, slide_number=2)
    ]
    
    json_data = create_test_json([("Section 1", elements)])
    
    layouts = organize_slides_by_number(json_data)
    
    assert len(layouts) == 2
    
    # Slide 1
    assert layouts[0].slide_number == 1
    assert layouts[0].layout_type == "base_with_kpis"
    assert len(layouts[0].elements) == 2
    
    # Slide 2
    assert layouts[1].slide_number == 2
    assert layouts[1].layout_type == "grid_2x2"
    assert len(layouts[1].elements) == 2


def test_organize_slides_full_slide_layout():
    """Test that single element on slide gets full_slide layout"""
    elements = [
        create_test_element(1, slide_number=1),
        create_test_element(2, slide_number=1),
        create_test_element(3, slide_number=2)  # Single element on slide 2
    ]
    
    json_data = create_test_json([("Section 1", elements)])
    
    layouts = organize_slides_by_number(json_data)
    
    assert len(layouts) == 2
    assert layouts[1].layout_type == "full_slide"  # Slide 2 has single element


def test_organize_slides_mixed_sections():
    """Test organizing elements from multiple sections"""
    section1_elements = [
        create_test_element(1, slide_number=1, section_name="Section 1"),
        create_test_element(2, slide_number=2, section_name="Section 1")
    ]
    
    section2_elements = [
        create_test_element(3, slide_number=2, section_name="Section 2"),
        create_test_element(4, slide_number=3, section_name="Section 2")
    ]
    
    json_data = create_test_json([
        ("Section 1", section1_elements),
        ("Section 2", section2_elements)
    ])
    
    layouts = organize_slides_by_number(json_data)
    
    assert len(layouts) == 3
    
    # Slide 1: 1 element from Section 1
    assert layouts[0].slide_number == 1
    assert len(layouts[0].elements) == 1
    
    # Slide 2: 1 from Section 1, 1 from Section 2
    assert layouts[1].slide_number == 2
    assert len(layouts[1].elements) == 2
    
    # Slide 3: 1 element from Section 2
    assert layouts[2].slide_number == 3
    assert len(layouts[2].elements) == 1


def test_organize_slides_skips_unselected():
    """Test that unselected elements are skipped"""
    elements = [
        create_test_element(1, slide_number=1),
        {**create_test_element(2, slide_number=1), "selected": False},
        create_test_element(3, slide_number=2)
    ]
    
    json_data = create_test_json([("Section 1", elements)])
    
    layouts = organize_slides_by_number(json_data)
    
    # Should only have slides 1 and 2, not including unselected element
    assert len(layouts) == 2
    assert layouts[0].slide_number == 1
    assert len(layouts[0].elements) == 1  # Only element 1
    assert layouts[1].slide_number == 2
    assert len(layouts[1].elements) == 1  # Only element 3


# ============================================================================
# POSITION DATACLASS TESTS
# ============================================================================

def test_position_to_dict():
    """Test Position.to_dict() conversion"""
    pos = Position(left=1.0, top=2.0, width=3.0, height=4.0, quadrant=0)
    
    d = pos.to_dict()
    
    assert d["left"] == 1.0
    assert d["top"] == 2.0
    assert d["width"] == 3.0
    assert d["height"] == 4.0
    assert d["quadrant"] == 0


# ============================================================================
# SLIDE LAYOUT DATACLASS TESTS
# ============================================================================

def test_slide_layout_to_dict():
    """Test SlideLayout.to_dict() conversion"""
    elements = [create_test_element(1)]
    positions = {"1": Position(0, 0, 5, 5, 0)}
    
    layout = SlideLayout(
        slide_number=1,
        layout_type="grid_2x2",
        elements=elements,
        positions=positions
    )
    
    d = layout.to_dict()
    
    assert d["slide_number"] == 1
    assert d["layout_type"] == "grid_2x2"
    assert len(d["elements"]) == 1
    assert "1" in d["positions"]
    assert isinstance(d["positions"]["1"], dict)


# ============================================================================
# EDGE CASES
# ============================================================================

def test_organize_slides_empty_sections():
    """Test organizing with empty sections"""
    json_data = create_test_json([])
    
    layouts = organize_slides_by_number(json_data)
    
    assert len(layouts) == 0


def test_organize_slides_no_slide_numbers():
    """Elements without slide numbers are ignored"""
    # Elements without slide_number in config
    elements = [
        {"id": 1, "element_type": "commentary", "selected": True, "config": {}}
    ]
    
    json_data = create_test_json([("Section 1", elements)])
    
    layouts = organize_slides_by_number(json_data)
    assert layouts == []


# ============================================================================
# INTEGRATION TEST
# ============================================================================

def test_full_workflow_integration():
    """Test complete workflow with realistic data"""
    # Simulate output from slide_number_assigner
    elements = [
        # Slide 1 (first slide)
        create_test_element(1, "commentary", slide_number=1, section_name="Executive Summary"),
        create_test_element(2, "chart", slide_number=1, section_name="Executive Summary"),
        
        # Slide 2 (2x2 grid)
        create_test_element(3, "commentary", slide_number=2, section_name="Market Analysis"),
        create_test_element(4, "chart", slide_number=2, section_name="Market Analysis"),
        create_test_element(5, "table", slide_number=2, section_name="Market Analysis"),
        create_test_element(6, "chart", slide_number=2, section_name="Market Analysis"),
        
        # Slide 3 (full slide - single large table)
        create_test_element(7, "table", slide_number=3, section_name="Data Tables"),
    ]
    
    json_data = create_test_json([
        ("Executive Summary", elements[:2]),
        ("Market Analysis", elements[2:6]),
        ("Data Tables", elements[6:])
    ])
    
    layouts = organize_slides_by_number(json_data)
    
    # Verify structure
    assert len(layouts) == 3
    
    # Slide 1: First slide layout
    assert layouts[0].slide_number == 1
    assert layouts[0].layout_type == "base_with_kpis"
    assert len(layouts[0].elements) == 2
    assert len(layouts[0].positions) == 2
    
    # Slide 2: 2x2 grid
    assert layouts[1].slide_number == 2
    assert layouts[1].layout_type == "grid_2x2"
    assert len(layouts[1].elements) == 4
    assert len(layouts[1].positions) == 4
    
    # Slide 3: Full slide
    assert layouts[2].slide_number == 3
    assert layouts[2].layout_type == "full_slide"
    assert len(layouts[2].elements) == 1
    assert len(layouts[2].positions) == 1
    
    # Verify all positions are valid
    for layout in layouts:
        for elem_id, pos in layout.positions.items():
            assert pos.left >= 0
            assert pos.top >= 0
            assert pos.width > 0
            assert pos.height > 0
            assert 0 <= pos.quadrant <= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

#!/usr/bin/env python3
"""
Unit tests for slide_number_assigner module

Tests slide number assignment logic with various scenarios:
- Basic assignment with multiple sections
- Overflow handling
- First slide special handling
- Edge cases
"""

import pytest
import json
from hello.utils.slide_number_assigner import (
    assign_slide_numbers,
    get_slide_statistics,
    _can_fit_in_quadrant,
    _estimate_element_size,
    _build_layout_metrics,
)


# ============================================================================
# TEST FIXTURES
# ============================================================================

def create_test_element(element_type, element_id, display_order=0, config=None):
    """Helper to create test elements"""
    if config is None:
        config = {}
    
    return {
        "id": element_id,
        "element_type": element_type,
        "selected": True,
        "display_order": display_order,
        "config": config,
        "label": f"Test {element_type} {element_id}"
    }


def create_test_section(name, elements, display_order=0):
    """Helper to create test sections"""
    return {
        "name": name,
        "key": name,
        "display_order": display_order,
        "selected": True,
        "elements": elements
    }


def create_test_json(sections):
    """Helper to create test JSON structure"""
    return {
        "report": {
            "name": "Test Report",
            "property_type": "Industrial"
        },
        "sections": sections
    }


@pytest.fixture
def default_layout():
    """Provide a default layout metrics instance for helper functions."""
    json_data = create_test_json([])
    json_data["report"]["property_sub_type"] = "figures"
    return _build_layout_metrics(json_data)


# ============================================================================
# BASIC FUNCTIONALITY TESTS
# ============================================================================

def test_assign_slide_numbers_basic():
    """Test basic slide number assignment with two sections"""
    # Create test data: 2 sections with 2 elements each
    section1_elements = [
        create_test_element("commentary", 1, 0),
        create_test_element("chart", 2, 1)
    ]
    section2_elements = [
        create_test_element("chart", 3, 0),
        create_test_element("table", 4, 1)
    ]
    
    sections = [
        create_test_section("Section 1", section1_elements, 0),
        create_test_section("Section 2", section2_elements, 1)
    ]
    
    json_data = create_test_json(sections)
    
    # Assign slide numbers
    result = assign_slide_numbers(json_data)
    
    # Verify section 1 elements are on slide 1 (first slide capacity = 2)
    assert result["sections"][0]["elements"][0]["config"]["slide_number"] == 1
    assert result["sections"][0]["elements"][1]["config"]["slide_number"] == 1
    
    # Verify section 2 elements are on slide 2 (new slide for new section)
    assert result["sections"][1]["elements"][0]["config"]["slide_number"] == 2
    assert result["sections"][1]["elements"][1]["config"]["slide_number"] == 2


def test_assign_slide_numbers_with_overflow():
    """Test slide number assignment when elements exceed slide capacity"""
    # Create section with 5 elements (more than regular slide capacity of 4)
    elements = [
        create_test_element("commentary", i, i)
        for i in range(5)
    ]
    
    sections = [create_test_section("Section 1", elements, 0)]
    json_data = create_test_json(sections)
    
    # Assign slide numbers
    result = assign_slide_numbers(json_data)
    
    # First 2 elements on slide 1 (first slide capacity = 2)
    assert result["sections"][0]["elements"][0]["config"]["slide_number"] == 1
    assert result["sections"][0]["elements"][1]["config"]["slide_number"] == 1
    
    # Next 4 elements on slide 2 (regular capacity = 4)
    assert result["sections"][0]["elements"][2]["config"]["slide_number"] == 2
    assert result["sections"][0]["elements"][3]["config"]["slide_number"] == 2
    assert result["sections"][0]["elements"][4]["config"]["slide_number"] == 2


def test_first_slide_special_capacity():
    """Test that first slide has capacity of 2"""
    # Create section with 3 elements
    elements = [
        create_test_element("commentary", 1, 0),
        create_test_element("chart", 2, 1),
        create_test_element("table", 3, 2)
    ]
    
    sections = [create_test_section("Section 1", elements, 0)]
    json_data = create_test_json(sections)
    
    # Assign slide numbers
    result = assign_slide_numbers(json_data)
    
    # First 2 elements on slide 1
    assert result["sections"][0]["elements"][0]["config"]["slide_number"] == 1
    assert result["sections"][0]["elements"][1]["config"]["slide_number"] == 1
    
    # Third element on slide 2
    assert result["sections"][0]["elements"][2]["config"]["slide_number"] == 2


# ============================================================================
# DISPLAY ORDER TESTS
# ============================================================================

def test_display_order_respected():
    """Test that display_order is respected for sections and elements"""
    # Create sections with non-sequential display orders
    section1_elements = [
        create_test_element("commentary", 1, 1),  # display_order = 1
        create_test_element("chart", 2, 0)        # display_order = 0 (should be first)
    ]
    section2_elements = [
        create_test_element("table", 3, 0)
    ]
    
    sections = [
        create_test_section("Section 2", section2_elements, 1),  # display_order = 1
        create_test_section("Section 1", section1_elements, 0)   # display_order = 0 (should be first)
    ]
    
    json_data = create_test_json(sections)
    
    # Assign slide numbers
    result = assign_slide_numbers(json_data)
    
    # Verify Section 1 (display_order 0) is processed first
    # Its elements should be on slide 1
    section1_in_result = next(s for s in result["sections"] if s["name"] == "Section 1")
    assert section1_in_result["elements"][0]["id"] == 2  # chart (display_order 0)
    assert section1_in_result["elements"][1]["id"] == 1  # commentary (display_order 1)
    
    # Both should be on slide 1
    assert section1_in_result["elements"][0]["config"]["slide_number"] == 1
    assert section1_in_result["elements"][1]["config"]["slide_number"] == 1


# ============================================================================
# SIZE ESTIMATION TESTS
# ============================================================================

def test_estimate_element_size_commentary(default_layout):
    """Test size estimation for commentary elements"""
    element = create_test_element("commentary", 1, config={
        "commentary_text": "A" * 500  # 500 characters
    })
    
    width, height = _estimate_element_size(element, default_layout)
    
    # Commentary should use available width
    assert width > 0
    # Height should scale with text length
    assert height > 1.0  # More than minimum


def test_estimate_element_size_chart(default_layout):
    """Test size estimation for chart elements"""
    element = create_test_element("chart", 1, config={
        "chart_type": "Line - Single axis"
    })
    
    width, height = _estimate_element_size(element, default_layout)
    
    # Charts have minimum dimensions
    assert width >= 3.5
    assert height >= 2.5


def test_estimate_element_size_table(default_layout):
    """Test size estimation for table elements"""
    element = create_test_element("table", 1, config={
        "table_data": [
            {"col1": "A", "col2": "B", "col3": "C"},
            {"col1": "D", "col2": "E", "col3": "F"}
        ]
    })
    
    width, height = _estimate_element_size(element, default_layout)
    
    # Table size should be based on data
    assert width > 0
    assert height > 0


# ============================================================================
# FIT CHECKING TESTS
# ============================================================================

def test_can_fit_in_quadrant_small_commentary(default_layout):
    """Test that small commentary fits in quadrant"""
    element = create_test_element("commentary", 1, config={
        "commentary_text": "Short text"
    })
    
    assert _can_fit_in_quadrant(element, default_layout) is True


def test_can_fit_in_quadrant_large_commentary(default_layout):
    """Test that large commentary can still fit (vertical overflow allowed)"""
    element = create_test_element("commentary", 1, config={
        "commentary_text": "A" * 5000  # Very long text
    })
    
    # Commentary can overflow vertically, so should still "fit"
    assert _can_fit_in_quadrant(element, default_layout) is True


def test_can_fit_in_quadrant_regular_chart(default_layout):
    """Test that regular chart requires more than a single quadrant"""
    element = create_test_element("chart", 1, config={
        "chart_type": "Line - Single axis"
    })
    
    assert _can_fit_in_quadrant(element, default_layout) is False


def test_can_fit_in_quadrant_wide_table(default_layout):
    """Test that wide table can fit (horizontal overflow allowed)"""
    # Create table with many columns
    row = {f"col{i}": "X" for i in range(20)}
    element = create_test_element("table", 1, config={
        "table_data": [row] * 10
    })
    
    # Tables can overflow horizontally
    assert _can_fit_in_quadrant(element, default_layout) is True


# ============================================================================
# EDGE CASES
# ============================================================================

def test_empty_sections():
    """Test handling of empty sections"""
    json_data = create_test_json([])
    
    result = assign_slide_numbers(json_data)
    
    # Should return unchanged
    assert result["sections"] == []


def test_unselected_elements():
    """Test that unselected elements are skipped"""
    elements = [
        create_test_element("commentary", 1, 0),
        {**create_test_element("chart", 2, 1), "selected": False},
        create_test_element("table", 3, 2)
    ]
    
    sections = [create_test_section("Section 1", elements, 0)]
    json_data = create_test_json(sections)
    
    result = assign_slide_numbers(json_data)
    
    # Unselected element should not have slide number
    assert "slide_number" not in result["sections"][0]["elements"][1]["config"]
    
    # Selected elements should have slide numbers
    assert result["sections"][0]["elements"][0]["config"]["slide_number"] == 1
    assert result["sections"][0]["elements"][2]["config"]["slide_number"] == 1


def test_unselected_sections():
    """Test that unselected sections are skipped"""
    section1_elements = [create_test_element("commentary", 1, 0)]
    section2_elements = [create_test_element("chart", 2, 0)]
    
    sections = [
        create_test_section("Section 1", section1_elements, 0),
        {**create_test_section("Section 2", section2_elements, 1), "selected": False}
    ]
    
    json_data = create_test_json(sections)
    
    result = assign_slide_numbers(json_data)
    
    # Section 1 should have slide numbers
    assert result["sections"][0]["elements"][0]["config"]["slide_number"] == 1
    
    # Section 2 elements should not have slide numbers
    assert "slide_number" not in result["sections"][1]["elements"][0]["config"]


# ============================================================================
# STATISTICS TESTS
# ============================================================================

def test_get_slide_statistics():
    """Test statistics generation"""
    elements = [
        create_test_element("commentary", 1, 0, {"slide_number": 1}),
        create_test_element("chart", 2, 1, {"slide_number": 1}),
        create_test_element("table", 3, 2, {"slide_number": 2})
    ]
    
    sections = [create_test_section("Section 1", elements, 0)]
    json_data = create_test_json(sections)
    
    stats = get_slide_statistics(json_data)
    
    assert stats["total_slides"] == 2
    assert stats["total_elements"] == 3
    assert 1 in stats["elements_by_slide"]
    assert 2 in stats["elements_by_slide"]
    assert len(stats["elements_by_slide"][1]) == 2
    assert len(stats["elements_by_slide"][2]) == 1


# ============================================================================
# INTEGRATION TEST WITH SAMPLE JSON
# ============================================================================

def test_sample_json_integration():
    """Test with sample JSON structure from the project"""
    sample_json = {
        "report": {
            "name": "Industrial Report",
            "property_type": "Industrial"
        },
        "sections": [
            {
                "name": "Executive Summary",
                "display_order": 0,
                "selected": True,
                "elements": [
                    {
                        "id": 1,
                        "element_type": "commentary",
                        "display_order": 0,
                        "selected": True,
                        "config": {"commentary_text": "Summary text"},
                        "label": "Summary"
                    },
                    {
                        "id": 2,
                        "element_type": "chart",
                        "display_order": 1,
                        "selected": True,
                        "config": {"chart_type": "Line - Single axis"},
                        "label": "Chart"
                    }
                ]
            },
            {
                "name": "Market Analysis",
                "display_order": 1,
                "selected": True,
                "elements": [
                    {
                        "id": 3,
                        "element_type": "chart",
                        "display_order": 0,
                        "selected": True,
                        "config": {"chart_type": "Bar Chart"},
                        "label": "Analysis Chart"
                    },
                    {
                        "id": 4,
                        "element_type": "table",
                        "display_order": 1,
                        "selected": True,
                        "config": {"table_data": []},
                        "label": "Data Table"
                    }
                ]
            }
        ]
    }
    
    result = assign_slide_numbers(sample_json)
    
    # Verify all elements have slide numbers
    for section in result["sections"]:
        for element in section["elements"]:
            assert "slide_number" in element["config"]
            assert element["config"]["slide_number"] >= 1
    
    # Get statistics
    stats = get_slide_statistics(result)
    assert stats["total_elements"] == 4
    assert stats["total_slides"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

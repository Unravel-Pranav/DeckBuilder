#!/usr/bin/env python3
"""
Test with user's actual JSON to demonstrate the fix
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from slide_number_assigner import assign_slide_numbers, print_slide_assignments


def main():
    # User's JSON data
    user_json = {
        "report": {
            "id": 4,
            "name": "testris_12345",
            "property_type": "Industrial"
        },
        "sections": [
            {
                "id": 58,
                "key": "test1234",
                "name": "test1234",
                "display_order": 0,
                "selected": True,
                "elements": [
                    {
                        "id": 184,
                        "element_type": "commentary",
                        "label": "Commentary",
                        "selected": True,
                        "display_order": 0,
                        "config": {}
                    },
                    {
                        "id": 185,
                        "element_type": "chart",
                        "label": "Chart Preview",
                        "selected": True,
                        "display_order": 1,
                        "config": {"chart_type": "Line - Single axis"}
                    }
                ]
            },
            {
                "id": 59,
                "key": "test123456",
                "name": "test123456",
                "display_order": 1,
                "selected": True,
                "elements": [
                    {
                        "id": 186,
                        "element_type": "commentary",
                        "label": "Commentary",
                        "selected": True,
                        "display_order": 0,
                        "config": {}
                    },
                    {
                        "id": 187,
                        "element_type": "chart",
                        "label": "Chart Preview",
                        "selected": True,
                        "display_order": 1,
                        "config": {"chart_type": "Line - Single axis"}
                    }
                ]
            },
            {
                "id": 60,
                "key": "test1234567",
                "name": "test1234567",
                "display_order": 2,
                "selected": True,
                "elements": [
                    {
                        "id": 188,
                        "element_type": "commentary",
                        "label": "Commentary",
                        "selected": True,
                        "display_order": 0,
                        "config": {}
                    },
                    {
                        "id": 189,
                        "element_type": "chart",
                        "label": "Chart Preview",
                        "selected": True,
                        "display_order": 1,
                        "config": {"chart_type": "Line - Single axis"}
                    }
                ]
            },
            {
                "id": 61,
                "key": "qwer12345",
                "name": "qwer12345",
                "display_order": 3,
                "selected": True,
                "elements": [
                    {
                        "id": 190,
                        "element_type": "table",
                        "label": "Data Table",
                        "selected": True,
                        "display_order": 0,
                        "config": {"table_data": [{"metric": "Test"}]}
                    },
                    {
                        "id": 191,
                        "element_type": "table",
                        "label": "Data Table",
                        "selected": True,
                        "display_order": 1,
                        "config": {"table_data": [{"metric": "Test2"}]}
                    }
                ]
            }
        ]
    }
    
    print("="*80)
    print("TESTING WITH USER'S JSON DATA")
    print("="*80)
    print("\nInput:")
    print(f"  4 sections with 2 elements each = 8 total elements")
    print(f"  Expected: Should fit in 2 slides (2 on slide 1, 4 on slide 2, 2 on slide 3)")
    print()
    
    # Assign slide numbers
    result = assign_slide_numbers(user_json)
    
    # Print results
    print_slide_assignments(result)
    
    # Verify the fix
    print("="*80)
    print("VERIFICATION")
    print("="*80)
    
    slide_1_elements = []
    slide_2_elements = []
    slide_3_elements = []
    
    for section in result["sections"]:
        for element in section["elements"]:
            slide_num = element["config"].get("slide_number")
            if slide_num == 1:
                slide_1_elements.append(f"Section '{section['name']}' - {element['element_type']} ({element['id']})")
            elif slide_num == 2:
                slide_2_elements.append(f"Section '{section['name']}' - {element['element_type']} ({element['id']})")
            elif slide_num == 3:
                slide_3_elements.append(f"Section '{section['name']}' - {element['element_type']} ({element['id']})")
    
    print(f"\n✅ Slide 1: {len(slide_1_elements)} elements (capacity: 2)")
    for elem in slide_1_elements:
        print(f"   - {elem}")
    
    print(f"\n✅ Slide 2: {len(slide_2_elements)} elements (capacity: 4)")
    for elem in slide_2_elements:
        print(f"   - {elem}")
    
    print(f"\n✅ Slide 3: {len(slide_3_elements)} elements (capacity: 4)")
    for elem in slide_3_elements:
        print(f"   - {elem}")
    
    # Check if sections are sharing slides
    print("\n" + "="*80)
    print("SECTION SHARING ANALYSIS")
    print("="*80)
    
    sections_on_slide_1 = set()
    sections_on_slide_2 = set()
    sections_on_slide_3 = set()
    
    for section in result["sections"]:
        section_name = section["name"]
        for element in section["elements"]:
            slide_num = element["config"].get("slide_number")
            if slide_num == 1:
                sections_on_slide_1.add(section_name)
            elif slide_num == 2:
                sections_on_slide_2.add(section_name)
            elif slide_num == 3:
                sections_on_slide_3.add(section_name)
    
    print(f"\nSlide 1: Sections {sections_on_slide_1}")
    print(f"Slide 2: Sections {sections_on_slide_2}")
    print(f"Slide 3: Sections {sections_on_slide_3}")
    
    if len(sections_on_slide_2) > 1:
        print(f"\n✅ SUCCESS: Multiple sections ({', '.join(sections_on_slide_2)}) are sharing slide 2!")
    else:
        print(f"\n⚠️  WARNING: Only one section on slide 2")
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)


if __name__ == "__main__":
    main()


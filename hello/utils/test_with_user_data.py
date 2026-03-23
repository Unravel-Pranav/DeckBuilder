#!/usr/bin/env python3
"""
Integration test with user's sample JSON data

This script demonstrates the complete workflow:
1. Load sample JSON
2. Assign slide numbers
3. Organize slides
4. Display results
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from slide_number_assigner import assign_slide_numbers, print_slide_assignments
from slide_organizer import organize_slides_by_number, print_layout_summary


def load_sample_json():
    """Load the sample JSON from the project"""
    sample_path = Path(__file__).parent.parent.parent.parent / "sample_json_generating_ppt.json"
    
    if sample_path.exists():
        with open(sample_path, 'r') as f:
            return json.load(f)
    else:
        print(f"Sample JSON not found at: {sample_path}")
        print("Using built-in test data instead.")
        return create_test_data()


def create_test_data():
    """Create test data matching the sample structure"""
    return {
        "report": {
            "id": 5,
            "name": "Industrial Market Report",
            "template_name": "Industrial Template",
            "property_type": "Industrial",
            "defined_markets": ["Kansas City Industrial"],
            "quarter": "2025 Q3"
        },
        "sections": [
            {
                "id": 71,
                "key": "Executive Summary",
                "name": "Executive Summary",
                "display_order": 0,
                "selected": True,
                "elements": [
                    {
                        "id": 207,
                        "element_type": "commentary",
                        "label": "Executive Summary Commentary",
                        "selected": True,
                        "display_order": 0,
                        "config": {
                            "commentary_text": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
                        }
                    },
                    {
                        "id": 208,
                        "element_type": "chart",
                        "label": "Executive Summary Chart",
                        "selected": True,
                        "display_order": 1,
                        "config": {
                            "chart_type": "Line - Single axis",
                            "chart_name": "Vacancy and Absorption Trends"
                        }
                    }
                ]
            },
            {
                "id": 72,
                "key": "Net Absorption",
                "name": "Net Absorption",
                "display_order": 1,
                "selected": True,
                "elements": [
                    {
                        "id": 209,
                        "element_type": "commentary",
                        "label": "Net Absorption Commentary",
                        "selected": True,
                        "display_order": 0,
                        "config": {
                            "commentary_text": "Market absorption analysis showing strong demand trends across all submarkets.",
                        }
                    },
                    {
                        "id": 210,
                        "element_type": "chart",
                        "label": "Leasing Activity Chart",
                        "selected": True,
                        "display_order": 1,
                        "config": {
                            "chart_type": "Line - Single axis",
                            "chart_name": "Quarterly Leasing Activity"
                        }
                    }
                ]
            },
            {
                "id": 73,
                "key": "Asking Rent",
                "name": "Asking Rent",
                "display_order": 2,
                "selected": True,
                "elements": [
                    {
                        "id": 211,
                        "element_type": "table",
                        "label": "Market Stats Table",
                        "selected": True,
                        "display_order": 0,
                        "config": {
                            "table_data": [
                                {"metric": "Vacancy Rate", "current": "12.8%", "previous": "13.2%", "change": "-0.4%"},
                                {"metric": "Avg Rent PSF", "current": "$68.50", "previous": "$67.80", "change": "+$0.70"},
                                {"metric": "Net Absorption", "current": "2.4M SF", "previous": "2.2M SF", "change": "+0.2M SF"}
                            ]
                        }
                    }
                ]
            }
        ]
    }


def main():
    """Main test function"""
    print("\n" + "="*80)
    print("SLIDE NUMBER ASSIGNMENT & ORGANIZATION TEST")
    print("="*80)
    
    # Load sample data
    print("\n📂 Loading sample JSON...")
    json_data = load_sample_json()
    
    print(f"   Report: {json_data['report']['name']}")
    print(f"   Sections: {len(json_data['sections'])}")
    
    total_elements = sum(len(s.get('elements', [])) for s in json_data['sections'])
    print(f"   Total elements: {total_elements}")
    
    # Step 1: Assign slide numbers
    print("\n" + "="*80)
    print("STEP 1: ASSIGNING SLIDE NUMBERS")
    print("="*80)
    
    json_with_numbers = assign_slide_numbers(json_data)
    
    # Print detailed assignments
    print_slide_assignments(json_with_numbers)
    
    # Step 2: Organize slides
    print("\n" + "="*80)
    print("STEP 2: ORGANIZING SLIDE LAYOUTS")
    print("="*80)
    
    layouts = organize_slides_by_number(json_with_numbers)
    
    # Print layout summary
    print_layout_summary(layouts)
    
    # Step 3: Export results
    print("\n" + "="*80)
    print("STEP 3: EXPORTING RESULTS")
    print("="*80)
    
    # Export assigned JSON
    output_dir = Path(__file__).parent / "test_output"
    output_dir.mkdir(exist_ok=True)
    
    assigned_json_path = output_dir / "json_with_slide_numbers.json"
    with open(assigned_json_path, 'w') as f:
        json.dump(json_with_numbers, f, indent=2)
    print(f"✅ Exported JSON with slide numbers: {assigned_json_path}")
    
    # Export layouts
    from slide_organizer import export_layouts_to_json
    layouts_json_path = output_dir / "slide_layouts.json"
    export_layouts_to_json(layouts, str(layouts_json_path))
    print(f"✅ Exported slide layouts: {layouts_json_path}")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"✓ Processed {len(json_data['sections'])} sections")
    print(f"✓ Assigned slide numbers to {total_elements} elements")
    print(f"✓ Created {len(layouts)} slide layouts")
    print(f"✓ Output files saved to: {output_dir}")
    
    # Breakdown by slide
    print("\nSlide Breakdown:")
    for layout in layouts:
        print(f"  Slide {layout.slide_number}: {layout.layout_type} - {len(layout.elements)} elements")
    
    print("\n" + "="*80)
    print("TEST COMPLETE ✅")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()


import os
import sys
import json
from pathlib import Path
from datetime import datetime
import random

# Add the backend directory to the search path for imports
current_dir = Path(__file__).parent
backend_node_dir = current_dir.parent.parent
sys.path.insert(0, str(backend_node_dir))

from app.ppt_engine.ppt_helpers_utils.services.frontend_json_processor import FrontendJSONProcessor
from app.ppt_engine.ppt_helpers_utils.services.presentation_generator import PresentationGenerator

def create_custom_json():
    """
    Creates a custom JSON structure as requested:
    - Slide 1: Front Page (default)
    - Slide 2: 4 graphs/charts
    - Slide 3: 2 graphs/charts + commentary
    - Slide 4: 1 graph + commentary
    - Slide 5: 3 graphs + commentary
    - Slide 6: Full commentary with headings
    """
    return {
        "report": {
            "name": "Custom Layout Verification",
            "property_sub_type": "figures",
            "quarter": "Q1 2025"
        },
        "sections": [
            {
                "id": "section_4_charts",
                "name": "4 Charts Page",
                "display_order": 0,
                "layout_preference": "grid_2x2",
                "elements": [
                    {
                        "id": "chart_1",
                        "element_type": "chart",
                        "config": {"chart_type": "Bar Chart", "chart_data": [{"category": "A", "value": 10}, {"category": "B", "value": 20}]}
                    },
                    {
                        "id": "chart_2",
                        "element_type": "chart",
                        "config": {"chart_type": "Line - Single axis", "chart_data": [{"category": "A", "value": 15}, {"category": "B", "value": 25}]}
                    },
                    {
                        "id": "chart_3",
                        "element_type": "chart",
                        "config": {"chart_type": "Pie Chart", "chart_data": [{"category": "A", "value": 30}, {"category": "B", "value": 70}]}
                    },
                    {
                        "id": "chart_4",
                        "element_type": "chart",
                        "config": {"chart_type": "Donut Chart", "chart_data": [{"category": "A", "value": 40}, {"category": "B", "value": 60}]}
                    }
                ]
            },
            {
                "id": "section_2_charts_comm",
                "name": "2 Charts + Commentary",
                "display_order": 1,
                "layout_preference": "grid_2x2",
                "elements": [
                    {
                        "id": "chart_5",
                        "element_type": "chart",
                        "config": {"chart_type": "Stacked bar", "chart_data": [{"category": "A", "v1": 5, "v2": 5}, {"category": "B", "v1": 10, "v2": 10}]}
                    },
                    {
                        "id": "chart_6",
                        "element_type": "chart",
                        "config": {"chart_type": "Horizontal Bar", "chart_data": [{"category": "A", "value": 50}, {"category": "B", "value": 80}]}
                    },
                    {
                        "id": "comm_1",
                        "element_type": "commentary",
                        "config": {
                            "section_alias": "Market Insights",
                            "commentary_text": "This slide features two charts and this specific commentary block. The 2x2 grid layout should accommodate all three elements comfortably."
                        }
                    }
                ]
            },
            {
                "id": "section_1_chart_comm",
                "name": "1 Chart + Commentary",
                "display_order": 2,
                "layout_preference": "grid_2x2",
                "elements": [
                    {
                        "id": "chart_7",
                        "element_type": "chart",
                        "config": {"chart_type": "Combo - Single Bar + Line", "chart_data": [{"category": "A", "bar": 60, "line": 20}, {"category": "B", "bar": 90, "line": 30}]}
                    },
                    {
                        "id": "comm_2",
                        "element_type": "commentary",
                        "config": {
                            "section_alias": "Focused Analysis",
                            "commentary_text": "A single combo chart paired with detailed analysis. This setup is common for deep dives into specific metrics."
                        }
                    }
                ]
            },
            {
                "id": "section_3_charts_comm",
                "name": "3 Charts + Commentary",
                "display_order": 3,
                "layout_preference": "grid_2x2",
                "elements": [
                    {
                        "id": "chart_8",
                        "element_type": "chart",
                        "config": {"chart_type": "Line - Multi axis", "chart_data": [{"category": "A", "v1": 1, "v2": 10}, {"category": "B", "v1": 2, "v2": 20}]}
                    },
                    {
                        "id": "chart_9",
                        "element_type": "chart",
                        "config": {"chart_type": "Single Column Stacked Chart", "chart_data": [{"category": "Total", "v1": 30, "v2": 40, "v3": 30}]}
                    },
                    {
                        "id": "chart_10",
                        "element_type": "chart",
                        "config": {"chart_type": "Combo - Double Bar + Line", "chart_data": [{"category": "A", "b1": 10, "b2": 15, "line": 5}, {"category": "B", "b1": 20, "b2": 25, "line": 10}]}
                    },
                    {
                        "id": "comm_3",
                        "element_type": "commentary",
                        "config": {
                            "section_alias": "Comprehensive View",
                            "commentary_text": "Three distinct visualizations and a summary. The 2x2 grid will fill all slots with these four elements."
                        }
                    }
                ]
            },
            {
                "id": "section_full_comm",
                "name": "Full Commentary",
                "display_order": 4,
                "layout_preference": "full_width",
                "elements": [
                    {
                        "id": "comm_4",
                        "element_type": "commentary",
                        "config": {
                            "section_alias": "Strategic Outlook",
                            "commentary_text": "Headline: Market Resilience Continues\n\nDetailed paragraphs follow here. We observe a trend of flight-to-quality in the office sector, while industrial demand remains robust despite macroeconomic headwinds. Capital markets are showing signs of stabilization as interest rate volatility decreases.\n\n• Point 1: Vacancy rates remain compressed in prime submarkets.\n• Point 2: Construction deliveries are reaching a multi-year peak.\n• Point 3: Rent growth is moderating but remains positive across core assets."
                        }
                    }
                ]
            }
        ]
    }

def verify_custom_generation():
    print("🚀 Starting Custom PPT Generation Verification...")
    
    # 1. Setup paths
    templates_dir = current_dir / "ppt_helpers_utils" / "individual_templates"
    output_dir = backend_node_dir / "data" / "output_ppt"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Select front-page template
    front_page_options = ["first_slide_base", "snapshot_first_slide_base", "submarket_first_slide_base"]
    selected_front = random.choice(front_page_options)
    print(f"🎲 Using front-page template: {selected_front}")
    
    # 3. Create JSON and parse it
    json_data = create_custom_json()
    json_data["report"]["template_name"] = f"{selected_front}.pptx"
    
    processor = FrontendJSONProcessor(templates_dir=str(templates_dir))
    sections = processor.parse_frontend_json(json_data)
    
    # 4. Initialize generator
    generator = PresentationGenerator(
        output_dir=str(output_dir)
    )
    
    # 5. Generate PPT
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"CUSTOM_PPT_{timestamp}.pptx"
    
    print(f"🛠 Generating presentation: {output_filename}...")
    try:
        final_path = generator.generate_presentation(
            sections=sections,
            title=json_data["report"]["name"],
            output_filename=output_filename
        )
        print(f"✅ PRESENTATION COMPLETE: {final_path}")
        
        # Verify slide count using python-pptx
        from pptx import Presentation
        prs = Presentation(final_path)
        slide_count = len(prs.slides)
        file_size = os.path.getsize(final_path)
        
        print(f"📊 ACTUAL SLIDE COUNT: {slide_count}")
        print(f"📊 FILE SIZE: {file_size / 1024:.2f} KB")
        
        # Expected: 1 cover + 5 content slides = 6 slides total (ignoring possible 'last_slide' if imported)
        if slide_count >= 6:
            print("✨ SUCCESS! The presentation contains all requested pages.")
        else:
            print(f"❌ ERROR: Only {slide_count} slides were generated. Expected at least 6.")
            
    except Exception as e:
        print(f"❌ ERROR during generation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_custom_generation()

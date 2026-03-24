#!/usr/bin/env python3
"""
Frontend JSON Processor
Converts frontend JSON format to orchestrator format for PowerPoint generation
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from app.utils.formatting import format_label, format_table_cell_value, get_latest_complete_quarter

# Import from the ppt_helpers module
from app.ppt_engine.ppt_helpers_utils.ppt_helpers.slide_orchestrator import (
    Section,
    TextBlock,
    ChartBlock,
    TableBlock,
    ContentBlock,
)

# Import slide number assignment
from app.ppt_engine.utils.slide_number_assigner import assign_slide_numbers
from app.ppt_engine.ppt_helpers_utils.services.template_config import (
    get_title_strategy,
    should_exclude_element,
    get_slide_layout_config,
)


def _transform_table_data(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply all data transformations to table data BEFORE height calculation.

    This ensures height calculation uses the same text that will be rendered:
    - Column names (keys): format_label() → title case, underscores→spaces
    - Cell values: format_table_cell_value() → adds thousand separators and formats negatives as configured

    Centralizing transformations here prevents divergence between calculation and rendering.
    """
    if not data:
        return data

    transformed = []
    for row in data:
        new_row = {}
        for key, value in row.items():
            # Transform column name (key)
            new_key = str(key)
            # format_label(str(key))
            # Transform cell value
            new_value = format_table_cell_value(value)
            new_row[new_key] = new_value
        transformed.append(new_row)

    return transformed


class FrontendJSONProcessor:
    """
    Processes frontend JSON format and converts to orchestrator sections

    Frontend JSON structure:
    {
        "presentation": {...},
        "sections": [
            {
                "section_name": "...",
                "slide_number": 1,
                "layout_preference": "...",
                "elements": [
                    {
                        "element_type": "chart|table|commentary|title|kpi",
                        "config": {...},
                        "display_order": 0
                    }
                ]
            }
        ]
    }
    """

    def __init__(self, templates_dir: str = None):
        """
        Initialize processor

        Args:
            templates_dir: Path to templates directory
        """
        if templates_dir is None:
            # Default to individual_templates/ (chart-type-based templates)
            templates_dir = os.path.join(
                os.path.dirname(__file__), "..", "individual_templates"
            )
            templates_dir = os.path.abspath(templates_dir)

            if not os.path.exists(templates_dir):
                raise FileNotFoundError(
                    f"Templates directory not found: {templates_dir}"
                )

        self.templates_dir = templates_dir

        # Mapping from display names to template filenames
        # Includes both display names and direct template names for flexibility
        self.chart_type_mapping = {
            "Line - Single axis": "line_chart",
            "Line - Multi axis": "multi_line_chart",
            "Bar Chart": "bar_chart",
            "Horizontal Bar": "horizontal_bar_chart",
            "Stacked bar": "stacked_bar_chart",
            "Combo - Single Bar + Line": "combo_chart_singlebar_line",
            "Combo - Double Bar + Line": "combo_chart_doublebar_line",
            "Combo - Stacked Bar + Line": "combo_chart_stackedbar_line",
            "Combo - Area + Bar": "combo_chart _area_bar",
            "Pie Chart": "pie_chart",
            "Donut Chart": "donut_chart",
            "Single Column Stacked Chart": "Single_column_stacked_chart",
            # Direct template names (for when chart_type already contains template name)
            "multi_line_chart": "multi_line_chart",
            "line_chart": "line_chart",
            "bar_chart": "bar_chart",
            "horizontal_bar_chart": "horizontal_bar_chart",
            "stacked_bar_chart": "stacked_bar_chart",
            "combo_chart_singlebar_line": "combo_chart_singlebar_line",
            "combo_chart_doublebar_line": "combo_chart_doublebar_line",
            "combo_chart_stackedbar_line": "combo_chart_stackedbar_line",
            "combo_chart _area_bar": "combo_chart _area_bar",
            "pie_chart": "pie_chart",
            "donut_chart": "donut_chart",
            "Single_column_stacked_chart": "Single_column_stacked_chart",
        }

        self.table_type_mapping = {
            "": "table",  # Default table type
            "table": "table",
        }
        self.last_assigned_json_path: Optional[str] = None

    def parse_frontend_json(self, json_data: Dict[str, Any]) -> List[Section]:
        """
        Parse new JSON format and convert to orchestrator sections

        DATA-FIRST WORKFLOW:
        1. Create blocks with data FIRST (data is populated from config)
        2. Assign slide numbers using actual data dimensions from blocks
        3. Return sections with blocks that have data and slide numbers

        Args:
            json_data: JSON data with "sections" array

        Returns:
            List of Section objects for orchestrator
        """
        # STEP 0: Extract quarter information for use in default chart sources
        report = json_data.get("report", {})
        # Get the last completed quarter dynamically (e.g., "2025 Q4" -> flip to "Q4 2025")
        latest_quarter = get_latest_complete_quarter()  # Returns "YYYY QN" format
        # Flip to "QN YYYY" format for consistency with existing code
        parts = latest_quarter.split()
        default_quarter = f"{parts[1]} {parts[0]}" if len(parts) == 2 else latest_quarter
        self.current_quarter = report.get("quarter", default_quarter)

        # Extract property_sub_type for element filtering
        self.current_property_sub_type = report.get("property_sub_type", "Figures")

        # Extract sections from new format
        sections_data = json_data.get("sections", [])

        if not sections_data:
            raise ValueError("No sections found in JSON data")

        print("\n📊 STEP 1: Creating blocks with data (BEFORE slide assignment)...")
        print(f"{'=' * 60}")

        # STEP 1: Create blocks with data FIRST (before slide assignment)
        # This ensures data is available for accurate size estimation
        orchestrator_sections = []
        figure_counter = 1
        all_blocks_by_element_id = {}  # Track blocks by element ID for slide assignment

        # Track processing for debug logging
        print(f"\n{'=' * 60}")
        print("📋 SECTION PROCESSING SUMMARY")
        print(f"{'=' * 60}")
        processed_count = 0
        skipped_count = 0
        skipped_reasons = []

        for idx, section_data in enumerate(sections_data):
            section_name = section_data.get(
                "sectionname_alias",
                section_data.get("name", section_data.get("key", f"Section {idx}")),
            )
            selected = section_data.get("selected", True)

            if not selected:
                print(f"⊘ Section {idx}: '{section_name}' - SKIPPED (selected=false)")
                skipped_count += 1
                skipped_reasons.append((section_name, "not selected"))
                continue

            print(f"\n📊 Processing Section {idx}: '{section_name}'")
            print(f"   Display Order: {section_data.get('display_order', 'N/A')}")
            print(f"   Elements: {len(section_data.get('elements', []))}")

            # Add default layout preference
            if "layout_preference" not in section_data:
                section_data["layout_preference"] = "Content (2x2 Grid)"

            # Force first slide to use base template
            if idx == 0:
                section_data["layout_preference"] = "First Slide (Base with KPIs)"
                section_data["is_first_slide"] = True

            # Create blocks with data (data is populated from element config)
            section, figure_counter, blocks_map = self._process_section_with_blocks(
                section_data, figure_counter
            )

            # Store blocks by element ID for slide assignment
            for element_id, block in blocks_map.items():
                all_blocks_by_element_id[element_id] = block

            if section and section.blocks:
                orchestrator_sections.append(section)
                processed_count += 1
                print(
                    f"   ✅ Section added to presentation with {len(section.blocks)} blocks (all with data)"
                )
            else:
                skipped_count += 1
                skipped_reasons.append(
                    (
                        section_name,
                        "all elements empty - section NOT added to presentation",
                    )
                )
                print("   ❌ Section NOT added - all elements have empty/no data")

        print(f"\n{'=' * 60}")
        print("BLOCK CREATION COMPLETE:")
        print(f"  ✅ Processed: {processed_count} sections")
        print(f"  ❌ Skipped: {skipped_count} sections")
        if skipped_reasons:
            print("\nSkipped Sections:")
            for name, reason in skipped_reasons:
                print(f"  - {name}: {reason}")
        print(f"{'=' * 60}\n")

        # STEP 2: Assign slide numbers using blocks with actual data dimensions
        print("\n🎯 STEP 2: Assigning slide numbers using actual data dimensions...")
        print(f"{'=' * 60}\n")

        # Update JSON with slide numbers using blocks that have data
        json_data = self._assign_slide_numbers_with_blocks(
            json_data, all_blocks_by_element_id
        )
        self._export_final_assigned_json(json_data)

        # STEP 3: Update blocks with assigned slide numbers from JSON
        print("\n🔄 STEP 3: Updating blocks with assigned slide numbers...")
        # Use updated json_data which contains the assigned slide numbers
        updated_sections = json_data.get("sections", [])
        for section in orchestrator_sections:
            for block in section.blocks:
                # Find corresponding element in JSON to get slide number and layout
                element_id = block.id
                for section_data in updated_sections:
                    elements = section_data.get("elements", [])
                    for element in elements:
                        if str(element.get("id")) == str(element_id):
                            config = element.get("config", {})
                            slide_num = config.get("slide_number")
                            layout = config.get("layout")

                            if not hasattr(block, "metadata") or not isinstance(
                                block.metadata, dict
                            ):
                                block.metadata = {}

                            if slide_num is not None:
                                block.metadata["slide_number"] = slide_num
                                print(
                                    f"   ✓ Block {element_id}: assigned to slide {slide_num}"
                                )

                            if layout:
                                block.metadata["layout"] = layout
                                print(
                                    f"   ✓ Block {element_id}: layout set to {layout}"
                                )
                            break

        return orchestrator_sections

    def _export_final_assigned_json(self, json_data: Dict[str, Any]) -> None:
        """Persist final slide-assigned JSON for debugging and traceability."""
        try:
            output_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "output_ppt")
            )
            os.makedirs(output_dir, exist_ok=True)

            report = json_data.get("report", {}) if isinstance(json_data, dict) else {}
            raw_name = (
                report.get("name")
                or report.get("title")
                or report.get("template_name")
                or "presentation"
            )
            safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(raw_name)).strip("_")
            if not safe_name:
                safe_name = "presentation"

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(
                output_dir, f"final_assigned_json_{safe_name}_{timestamp}.json"
            )

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)

            self.last_assigned_json_path = output_path
            print(f"   🧾 Final assigned JSON exported: {output_path}")
        except Exception as e:
            print(f"   ⚠ Could not export final assigned JSON: {e}")

    def _extract_sections_from_slides(
        self, slides_dict: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract sections from Streamlit slides format

        Args:
            slides_dict: Dictionary of slides from Streamlit format

        Returns:
            List of section dictionaries
        """
        all_sections = []

        # Sort slides by slide_number
        sorted_slides = sorted(
            slides_dict.items(), key=lambda x: x[1].get("slide_number", 0)
        )

        for slide_key, slide_data in sorted_slides:
            sections = slide_data.get("sections", {})
            layout_type = slide_data.get("layout_type")

            for section_key, section_data in sections.items():
                # Convert elements dict to list with proper structure
                elements_dict = section_data.get("elements", {})
                elements_list = []

                for elem_key, elem_data in elements_dict.items():
                    # Map Streamlit format to frontend format
                    element = {
                        "id": elem_key,
                        "element_type": elem_data.get("type", ""),
                        "label": elem_data.get("title", ""),
                        "selected": True,
                        "display_order": elem_data.get("priority", 0),
                        "config": {},
                    }

                    # Map fields to config based on type
                    elem_type = elem_data.get("type", "")

                    if elem_type in ["commentary", "text"]:
                        element["config"]["content"] = elem_data.get("content", "")
                    elif elem_type == "chart":
                        element["config"]["chart_type"] = elem_data.get(
                            "chart_type", ""
                        )
                        element["config"]["figure_name"] = elem_data.get(
                            "figure_name", ""
                        )
                        element["config"]["figure_source"] = elem_data.get(
                            "figure_source", ""
                        )
                    elif elem_type == "table":
                        element["config"]["table_type"] = elem_data.get(
                            "table_type", ""
                        )
                        element["config"]["rows"] = elem_data.get("rows", 10)
                        element["config"]["columns"] = elem_data.get("columns", 5)

                    elements_list.append(element)

                # Create section in frontend format
                section_converted = {
                    "section_name": section_data.get(
                        "sectionname_alias",
                        section_data.get("name", "Untitled Section"),
                    ),
                    "layout_preference": layout_type,
                    "elements": elements_list,
                }

                all_sections.append(section_converted)

        return all_sections

    def _process_section_with_blocks(
        self, section_data: Dict[str, Any], figure_counter: int
    ) -> Tuple[Optional[Section], int, Dict[str, ContentBlock]]:
        """
        Process a section and create blocks with data, returning blocks map for slide assignment.

        Returns:
            Tuple of (Section, figure_counter, blocks_map)
            blocks_map: Dict mapping element_id to ContentBlock
        """
        section, figure_counter = self._process_section(section_data, figure_counter)

        # Create blocks map
        blocks_map = {}
        if section:
            for block in section.blocks:
                blocks_map[block.id] = block

        return section, figure_counter, blocks_map

    def _process_section(
        self, section_data: Dict[str, Any], figure_counter: int
    ) -> Tuple[Optional[Section], int]:
        """
        Process a single section from new JSON format

        Args:
            section_data: Section data from JSON

        Returns:
            Section object or None if empty
        """
        section_name = section_data.get(
            "sectionname_alias",
            section_data.get(
                "name", section_data.get("section_name", "Untitled Section")
            ),
        )
        elements_data = section_data.get("elements", [])

        if not elements_data:
            print(f"⚠️  Section '{section_name}' has no elements, skipping")
            return None, figure_counter

        # Sort elements by display_order
        elements_data_sorted = sorted(
            elements_data, key=lambda x: x.get("display_order", 0)
        )

        print(
            f"   [DEBUG] Section '{section_name}' processing {len(elements_data_sorted)} elements"
        )

        # Extract layout_preference from section level or first element's config
        layout_pref = section_data.get("layout_preference")
        if not layout_pref and elements_data_sorted:
            # Fallback: get from first element's config
            first_elem_config = elements_data_sorted[0].get("config", {})
            layout_pref = first_elem_config.get("layout_preference")

        # Convert elements to content blocks
        # Data is now embedded in each element's config
        content_blocks = []

        for element in elements_data_sorted:
            if not element.get("selected", True):
                continue  # Skip unselected elements

            block, figure_counter = self._create_content_block(element, figure_counter)
            if block:
                content_blocks.append(block)

        if not content_blocks:
            print(
                f"⊘  Section '{section_name}' SKIPPED - all elements have empty/no data, section block will NOT be created"
            )
            return None, figure_counter

        print(
            f"   ✅ Section '{section_name}' has {len(content_blocks)} valid blocks with data"
        )

        # Get section title visibility from config based on property_sub_type
        layout_config = get_slide_layout_config(self.current_property_sub_type)
        show_title = layout_config.show_section_titles

        # Create section
        section = Section(
            id=f"section_{hash(section_name)}",
            title=section_name,
            blocks=content_blocks,
            layout_preference=layout_pref,
            style={"show_title": show_title},
        )

        return section, figure_counter

    def _create_content_block(
        self, element: Dict[str, Any], figure_counter: int
    ) -> Tuple[Optional[ContentBlock], int]:
        """
        Create a content block from an element

        Args:
            element: Element data from JSON

        Returns:
            ContentBlock (TextBlock, ChartBlock, or TableBlock) or None
        """
        element_type = element.get("element_type", "")
        element_id = element.get("id", f"elem_{hash(str(element))}")
        element_label = element.get("label", "")  # Extract label for headings
        config = element.get("config", {})

        # Check if this element type should be excluded for current property_sub_type
        if should_exclude_element(self.current_property_sub_type, element_type):
            print(
                f"      ⊘ Skipping {element_type} element (excluded for property_sub_type={self.current_property_sub_type})"
            )
            return None, figure_counter

        # Extract slide number from config
        slide_number = config.get("slide_number")

        try:
            if element_type in ["commentary", "text", "title", "kpi", "summary"]:
                block = self._create_text_block(
                    element_id, element_type, config, element
                )

            elif element_type == "chart":
                # Extract data from config
                data = config.get("chart_data", [])
                # Skip chart elements with no data
                if not data or len(data) == 0:
                    print(
                        f"      ⊘ SKIPPING: Chart element {element_id} has NO chart_data - element will be excluded from presentation"
                    )
                    return None, figure_counter
                else:
                    print(
                        f"      ✅ Chart element {element_id} has {len(data)} data rows - will use for size estimation"
                    )
                block, figure_counter = self._create_chart_block(
                    element_id=element_id,
                    config=config,
                    data=data,
                    figure_counter=figure_counter,
                )

            elif element_type == "table":
                # Extract data from config
                data = config.get("table_data", [])
                # Skip table elements with no data
                if not data or len(data) == 0:
                    print(
                        f"      ⊘ SKIPPING: Table element {element_id} has NO table_data - element will be excluded from presentation"
                    )
                    return None, figure_counter
                else:
                    print(
                        f"      ✅ Table element {element_id} has {len(data)} data rows - will use for size estimation"
                    )
                
                # IMPORTANT: Transform data IN PLACE in the element config
                # This ensures ALL stages (assignment, orchestration, rendering) use
                # the exact same transformed data for consistent height calculations.
                transformed_data = _transform_table_data(data)
                config["table_data"] = transformed_data
                
                block, figure_counter = self._create_table_block(
                    element_id=element_id,
                    config=config,
                    data=transformed_data,  # Pass transformed data
                    figure_counter=figure_counter,
                )

            else:
                print(f"⚠️  Unknown element type: {element_type}")
                return None, figure_counter

            # Set label, display_order and slide number if block was created
            if block:
                # Set display_order from element (critical for section title placement)
                block.display_order = element.get("display_order", 0)
                
                if element_label:
                    block.label = element_label
                    # Update figure_name to reflect the new label if figure_number exists
                    if hasattr(block, "figure_number") and block.figure_number:
                        block.figure_name = (
                            f"Figure {block.figure_number}: {element_label}"
                        )
                # Store slide number and layout as metadata
                # Ensure metadata is a dict (it might be None or something else)
                if not hasattr(block, "metadata") or not isinstance(
                    block.metadata, dict
                ):
                    block.metadata = {}
                if slide_number is not None:
                    block.metadata["slide_number"] = slide_number
                # Extract layout from element config and store in block metadata
                layout = config.get("layout")
                if layout:
                    block.metadata["layout"] = layout
                    print(
                        f"      [DEBUG] Block {block.id}: Set layout={layout} from element config"
                    )
                else:
                    print(
                        f"      [DEBUG] Block {block.id}: No layout in element config"
                    )

            return block, figure_counter

        except Exception as e:
            print(f"❌ Error creating block for element {element_id}: {e}")
            return None, figure_counter

    def _assign_slide_numbers_with_blocks(
        self, json_data: Dict[str, Any], blocks_map: Dict[str, ContentBlock]
    ) -> Dict[str, Any]:
        """
        Assign slide numbers using blocks with actual data dimensions.

        This updates the JSON config with size information from blocks,
        then calls assign_slide_numbers which will use this data.

        Args:
            json_data: JSON data with sections
            blocks_map: Dict mapping element_id to ContentBlock with data

        Returns:
            Updated JSON with slide numbers assigned
        """
        # Update element configs with actual dimensions from blocks
        sections = json_data.get("sections", [])

        for section in sections:
            elements = section.get("elements", [])
            for element in elements:
                element_id = str(element.get("id", ""))
                if element_id in blocks_map:
                    block = blocks_map[element_id]
                    config = element.get("config", {})

                    # Update config with actual data dimensions for slide assignment
                    if hasattr(block, "data") and block.data:
                        if block.type.value == "table":
                            # Update table dimensions from actual data
                            if not config.get("table_data"):
                                config["table_data"] = block.data
                            # Update rows/columns from actual data
                            if block.data and len(block.data) > 0:
                                config["rows"] = len(block.data) + 1  # +1 for header
                                if isinstance(block.data[0], dict):
                                    config["columns"] = len(block.data[0].keys())
                        elif block.type.value == "chart":
                            # Update chart data
                            if not config.get("chart_data"):
                                config["chart_data"] = block.data

        # Now call assign_slide_numbers which will use the updated config with actual data
        print("   📐 Calling assign_slide_numbers with blocks that have actual data...")
        json_data = assign_slide_numbers(json_data)

        return json_data

    def _create_text_block(
        self,
        element_id: Any,
        element_type: str,
        config: Dict[str, Any],
        element: Dict[str, Any] = None,
    ) -> Optional[TextBlock]:
        """
        Create a TextBlock from element config

        Returns:
            TextBlock or None if content is empty (for commentary/text/summary types)
        """
        # Extract text content based on element type
        if element_type == "title":
            title = config.get("title", "")
            subtitle = config.get("subtitle", "")
            text = f"{title}\n{subtitle}" if subtitle else title
            bullet_points = []

        elif element_type == "kpi":
            kpi_value = config.get("kpi_value", "")
            kpi_label = config.get("kpi_label", "")
            text = f"►{kpi_value} {kpi_label}"
            bullet_points = []

        else:  # commentary, text, summary
            # For commentary: section_name from config is the heading, content/commentary_text is the description
            heading = config.get(
                "section_alias", config.get("section_name", element.get("label", ""))
            )
            print(f"   [DEBUG] Text block heading: '{heading}'")
            # Map commentary_text to content for new format
            content = (
                config.get("commentary_json")
                or config.get("commentary_text")
                or config.get("content")
                or element.get(
                    "section_commentary"
                )  # Added support for section_commentary at element level
                or ""
            )
            print(
                f"   [DEBUG] Text block content length: {len(content) if content else 0} chars"
            )

            # Skip commentary/text/summary elements with no content
            if not content or not content.strip():
                print(
                    f"      ⊘ SKIPPING: Commentary/text element {element_id} has NO content - element will be excluded from presentation"
                )
                return None

            # If content has bullets, split them out
            bullet_points = []
            if "\n•" in content or "\n-" in content:
                lines = content.split("\n")
                bullet_points = [
                    line.lstrip("•-• ").strip()
                    for line in lines
                    if line.strip().startswith(("•", "-"))
                ]
                # Non-bullet lines become additional description
                non_bullet_lines = [
                    line.strip()
                    for line in lines
                    if not line.strip().startswith(("•", "-")) and line.strip()
                ]
                if non_bullet_lines:
                    bullet_points = non_bullet_lines + bullet_points
            else:
                # No bullets - entire content becomes description
                if content:
                    bullet_points = [content]

            # text = heading, bullet_points = description paragraphs
            text = heading.strip() if heading else ""

        return TextBlock(
            id=str(element_id),
            text=text,  # Heading from label
            bullet_points=bullet_points,  # Description from content
        )

    def _create_chart_block(
        self,
        element_id: Any,
        config: Dict[str, Any],
        data: List[Dict] = None,
        figure_counter: int = 1,
    ) -> Tuple[Optional[ChartBlock], int]:
        """
        Create a ChartBlock from element config

        Returns None if data is empty - no block will be added to presentation.
        """
        # Skip if no data - don't create block
        if not data or len(data) == 0:
            print(
                f"      ⊘ SKIPPING: Chart {element_id} - no data, block will NOT be created"
            )
            return None, figure_counter

        chart_type = config.get("chart_type", "")

        if not chart_type:
            print(f"⚠️  Chart element {element_id} missing chart_type")
            return None, figure_counter

        # Map display name to template filename if needed
        template_base_name = self.chart_type_mapping.get(chart_type) or chart_type

        # Map chart type to template file
        template_filename = f"{template_base_name}.pptx"
        template_path = os.path.join(self.templates_dir, template_filename)

        # Enhanced logging for chart processing
        print(f"      [CHART] Element {element_id}:")
        print(f"         Chart Type: '{chart_type}'")
        print(f"         Template Base: '{template_base_name}'")
        print(f"         Template File: '{template_filename}'")
        print(f"         Data Rows: {len(data) if data else 0}")
        print(f"         Looking for: {template_path}")

        if not os.path.exists(template_path):
            print("         ❌ TEMPLATE NOT FOUND!")
            print(f"         Available templates in {self.templates_dir}:")
            import glob

            for f in sorted(glob.glob(os.path.join(self.templates_dir, "*.pptx"))):
                print(f"            - {os.path.basename(f)}")
            return None, figure_counter

        print("         ✅ Template found")

        # Extract axis titles and column keys from axisConfig
        axis_config = config.get("axisConfig", {})
        (
            primary_y_axis_title,
            secondary_y_axis_title,
            x_axis_title,
            y_axis_keys,
            x_axis_keys,
            is_multi_axis,
            primary_y_axis_format_code,
            secondary_y_axis_format_code,
        ) = self._extract_axis_titles(axis_config, chart_type=template_base_name)

        # Filter and sort data based on axisConfig
        if x_axis_keys or y_axis_keys:
            original_columns = len(data[0]) if data else 0
            data = self._filter_and_sort_chart_data(data, x_axis_keys, y_axis_keys)
            filtered_columns = len(data[0]) if data else 0
            print(
                f"         [DEBUG] Filtered data from {original_columns} to {filtered_columns} columns (preserving original order)"
            )

        # Create block with data (data is guaranteed to be non-empty at this point)
        block = ChartBlock(
            id=str(element_id),
            template_path=template_path,
            chart_type=chart_type,
            intrinsic_aspect_ratio=16 / 9,
            data=data,
            primary_y_axis_title=primary_y_axis_title,
            secondary_y_axis_title=secondary_y_axis_title,
            x_axis_title=x_axis_title,
            y_axis_keys=y_axis_keys,
            is_multi_axis=is_multi_axis,
            primary_y_axis_format_code=primary_y_axis_format_code,
            secondary_y_axis_format_code=secondary_y_axis_format_code,
        )

        # Derive figure naming metadata
        raw_label = (
            config.get("chart_label")
            or config.get("chart_name")
            or config.get("label")
            or ""
        )
        label_value = raw_label.strip() if isinstance(raw_label, str) else ""
        block.figure_number = figure_counter
        block.figure_label = label_value or None

        figure_text = f"Figure {figure_counter}"
        if label_value:
            figure_text = f"{figure_text}: {label_value}"
        block.figure_name = figure_text

        source_value = config.get("chart_source")
        if isinstance(source_value, str) and source_value.strip():
            block.figure_source = source_value.strip()
        else:
            flipped_quarter = " ".join(self.current_quarter.split(" ")[::-1])
            block.figure_source = f"Source: CBRE Research, {flipped_quarter}"

        print(
            f"         [DEBUG] ChartBlock created with {len(block.data) if block.data else 0} data rows, is_multi_axis={is_multi_axis}"
        )
        if primary_y_axis_title or secondary_y_axis_title or x_axis_title:
            print(
                f"         [DEBUG] Axis titles - Primary Y: '{primary_y_axis_title}', Secondary Y: '{secondary_y_axis_title}', X: '{x_axis_title}'"
            )

        return block, figure_counter + 1

    def _reorder_table_columns(
        self,
        data: List[Dict[str, Any]],
        column_sequence: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """
        Reorder columns in data rows based on sequence.

        Args:
            data: List of row dictionaries
            column_sequence: Ordered list of column names. If None or empty, data is unchanged.

        Returns:
            List of row dictionaries with keys reordered. Keys in sequence come first,
            followed by any extra keys not in the sequence (preserving their original order).
        """
        if not column_sequence or not data:
            return data

        sequence_set = set(column_sequence)
        reordered_data: List[Dict[str, Any]] = []

        for row in data:
            if not isinstance(row, dict):
                reordered_data.append(row)
                continue

            ordered_row: Dict[str, Any] = {}
            # First, add keys from the sequence in order
            for key in column_sequence:
                if key in row:
                    ordered_row[key] = row[key]
            # Then, add any extra keys not in the sequence (preserve original order)
            for key in row:
                if key not in sequence_set:
                    ordered_row[key] = row[key]

            reordered_data.append(ordered_row)

        return reordered_data

    def _create_table_block(
        self,
        element_id: Any,
        config: Dict[str, Any],
        data: List[Dict] = None,
        figure_counter: int = 1,
    ) -> Tuple[Optional[TableBlock], int]:
        """
        Create a TableBlock from element config

        Returns None if data is empty - no block will be added to presentation.
        """
        # Skip if no data - don't create block
        if not data or len(data) == 0:
            print(
                f"      ⊘ SKIPPING: Table {element_id} - no data, block will NOT be created"
            )
            return None, figure_counter

        # NOTE: Data transformation is now done in _create_content_block BEFORE this method
        # is called. This ensures all stages use the same transformed data.

        # Apply column sequence reordering if provided (for backward compatibility,
        # if table_columns_sequence is not present or empty, data remains unchanged)
        table_columns_sequence = config.get("table_columns_sequence")
        if table_columns_sequence:
            data = self._reorder_table_columns(data, table_columns_sequence)
            # Also update config so assignment phase sees reordered columns
            config["table_data"] = data
            print(
                f"      ✅ Table {element_id}: Reordered columns using sequence: {table_columns_sequence}"
            )

        table_type = config.get("table_type", "")

        # Map display name to template filename if needed
        template_base_name = self.table_type_mapping.get(
            table_type, table_type if table_type else "table"
        )

        # Infer rows and columns from data (data is guaranteed to be non-empty at this point)
        rows = config.get("rows") or len(data) + 1  # +1 for header
        # Get column count from first data row keys (actual data columns)
        if isinstance(data[0], dict):
            columns = config.get("columns") or len(data[0].keys())
        else:
            columns = config.get("columns") or (
                len(data[0]) if hasattr(data[0], "__len__") else 5
            )

        # Ensure rows and columns are never None
        if rows is None:
            rows = 10
        if columns is None:
            columns = 5

        template_filename = f"{template_base_name}.pptx"
        template_path = os.path.join(self.templates_dir, template_filename)

        if not os.path.exists(template_path):
            print(f"⚠️  Template not found: {template_path} (table_type: {table_type})")
            return None, figure_counter

        # Create block with data (data is guaranteed to be non-empty at this point)
        block = TableBlock(
            id=str(element_id),
            rows=rows,
            columns=columns,
            template_path=template_path,
            data=data,
        )

        # Derive figure naming metadata (similar to charts)
        raw_label = config.get("table_label") or config.get("label") or ""
        label_value = raw_label.strip() if isinstance(raw_label, str) else ""
        block.figure_number = figure_counter
        block.figure_label = label_value or None

        figure_text = f"Figure {figure_counter}"
        if label_value:
            figure_text = f"{figure_text}: {label_value}"
        block.figure_name = figure_text

        # Also set block.label for heading (used by _add_table_heading)
        block.label = label_value or None

        # Derive table source from config (similar to chart_source)
        source_value = config.get("table_source")
        if isinstance(source_value, str) and source_value.strip():
            block.table_source = source_value.strip()
        else:
            flipped_quarter = " ".join(self.current_quarter.split(" ")[::-1])
            block.table_source = f"Source: CBRE Research, {flipped_quarter}"

        print(
            f"         [DEBUG] TableBlock created with {len(block.data) if block.data else 0} data rows"
        )

        return block, figure_counter + 1

    def _extract_axis_titles(
        self, axis_config: Dict[str, Any], chart_type: str = ""
    ) -> Tuple[
        Optional[str],
        Optional[str],
        Optional[str],
        List[str],
        List[str],
        bool,
        Optional[str],
        Optional[str],
    ]:
        """
        Extract axis titles and column keys from axisConfig structure.

        Args:
            axis_config: Dictionary with xAxis and yAxis arrays
                Example:
                {
                    "xAxis": [{"key": "PERIOD", "name": "PERIOD"}],
                    "yAxis": [
                        {"key": "COL1", "name": "Primary Title", "isPrimary": true},
                        {"key": "COL2", "name": "Secondary Title", "isPrimary": false},
                        {"key": "COL3", "name": "Extra Column", "isPrimary": false}
                    ],
                    "isMultiAxis": true
                }
            chart_type: Chart type string (e.g., "combo_chart_doublebar_line")

        Returns:
            Tuple of (
                primary_y_axis_title,
                secondary_y_axis_title,
                x_axis_title,
                y_axis_keys,
                x_axis_keys,
                is_multi_axis,
                primary_y_axis_format_code,
                secondary_y_axis_format_code,
            )
            - y_axis_keys: Ordered list of column keys (primary first, then secondary)
            - x_axis_keys: List of x-axis column keys for data filtering and sorting
            - is_multi_axis: Whether to show secondary Y-axis (default True for backward compat)
            - Note: x_axis_title is always None by default (X-axis title update is disabled)
        """
        primary_y_axis_title: Optional[str] = None
        secondary_y_axis_title: Optional[str] = None
        x_axis_title: Optional[str] = None  # X-axis title disabled by default
        y_axis_keys: List[str] = []  # Ordered column keys for data selection
        x_axis_keys: List[str] = []  # X-axis column keys for filtering and sorting
        is_multi_axis: bool = True  # Default True for backward compatibility
        primary_y_axis_format_code: Optional[str] = None
        secondary_y_axis_format_code: Optional[str] = None

        if not axis_config:
            return (
                primary_y_axis_title,
                secondary_y_axis_title,
                x_axis_title,
                y_axis_keys,
                x_axis_keys,
                is_multi_axis,
                primary_y_axis_format_code,
                secondary_y_axis_format_code,
            )

        # Extract isMultiAxis flag (default True for backward compatibility)
        is_multi_axis = axis_config.get("isMultiAxis", True)

        # Extract Y-axis titles and keys from yAxis array
        y_axis_entries = axis_config.get("yAxis", [])

        # Special handling for double bar + line and stacked bar + line combo charts
        # Use 1st and last yAxis entries for axis titles (skip middle entries)
        if (
            chart_type in [
                "combo_chart_doublebar_line",
                "Combo - Double Bar + Line",
                "combo_chart_stackedbar_line",
                "Combo - Stacked Bar + Line",
            ]
            and len(y_axis_entries) >= 2
        ):
            # Primary title from first entry
            first_entry = y_axis_entries[0]
            if isinstance(first_entry, dict) and first_entry.get("name"):
                primary_y_axis_title = str(first_entry["name"]).strip()
            if isinstance(first_entry, dict) and first_entry.get("format_code"):
                primary_y_axis_format_code = str(first_entry["format_code"]).strip() or None
            # Secondary title from last entry (skip middle entries)
            last_entry = y_axis_entries[-1]
            if isinstance(last_entry, dict) and last_entry.get("name"):
                secondary_y_axis_title = str(last_entry["name"]).strip()
            if isinstance(last_entry, dict) and last_entry.get("format_code"):
                secondary_y_axis_format_code = str(last_entry["format_code"]).strip() or None

            # Build y_axis_keys in order for data selection
            for entry in y_axis_entries:
                if isinstance(entry, dict):
                    key = entry.get("key")
                    if key and key not in y_axis_keys:
                        y_axis_keys.append(str(key))
        else:
            # Default logic: separate primary and secondary entries based on isPrimary flag
            primary_entries: List[Dict[str, Any]] = []
            secondary_entries: List[Dict[str, Any]] = []

            for entry in y_axis_entries:
                if not isinstance(entry, dict):
                    continue

                is_primary = entry.get(
                    "isPrimary", True
                )  # Default to primary if not specified
                if is_primary:
                    primary_entries.append(entry)
                else:
                    secondary_entries.append(entry)

            # Set primary title (first primary entry)
            if primary_entries:
                name = primary_entries[0].get("name")
                if name:
                    primary_y_axis_title = str(name).strip()
                fmt = primary_entries[0].get("format_code")
                if fmt:
                    primary_y_axis_format_code = str(fmt).strip() or None

            # Set secondary title (first secondary entry)
            if secondary_entries:
                name = secondary_entries[0].get("name")
                if name:
                    secondary_y_axis_title = str(name).strip()
                fmt = secondary_entries[0].get("format_code")
                if fmt:
                    secondary_y_axis_format_code = str(fmt).strip() or None

            # For pie/donut charts, only use primary Y-axis for plotting values
            # This ensures only the isPrimary=true column is used for slice values
            is_pie_or_donut = chart_type.lower() in [
                "pie",
                "pie_chart",
                "donut",
                "donut_chart",
            ]

            # Build ordered y_axis_keys: primary keys first, then secondary keys
            # For pie/donut charts, only include primary keys (isPrimary=true)
            for entry in primary_entries:
                key = entry.get("key")
                if key and key not in y_axis_keys:
                    y_axis_keys.append(str(key))

            # Only add secondary keys for non-pie/donut charts
            if not is_pie_or_donut:
                for entry in secondary_entries:
                    key = entry.get("key")
                    if key and key not in y_axis_keys:
                        y_axis_keys.append(str(key))

        # Extract X-axis keys for data filtering and sorting
        x_axis_entries = axis_config.get("xAxis", [])
        for entry in x_axis_entries:
            if isinstance(entry, dict) and entry.get("key"):
                x_axis_keys.append(str(entry["key"]))

        # X-axis title extraction is disabled by default
        # Uncomment below to enable X-axis title updates from axisConfig:
        # if x_axis_entries and isinstance(x_axis_entries[0], dict):
        #     x_axis_name = x_axis_entries[0].get("name")
        #     if x_axis_name:
        #         x_axis_title = str(x_axis_name).strip()

        return (
            primary_y_axis_title,
            secondary_y_axis_title,
            x_axis_title,
            y_axis_keys,
            x_axis_keys,
            is_multi_axis,
            primary_y_axis_format_code,
            secondary_y_axis_format_code,
        )

    def _filter_and_sort_chart_data(
        self, data: List[Dict[str, Any]], x_axis_keys: List[str], y_axis_keys: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Filter chart data to only include columns defined in axisConfig.

        Note: Data order is preserved from the input. The data source is responsible
        for providing data in the desired order (e.g., chronological).

        Args:
            data: List of data row dictionaries
            x_axis_keys: List of x-axis column keys from axisConfig
            y_axis_keys: List of y-axis column keys from axisConfig

        Returns:
            Filtered list of data rows containing only axisConfig columns
        """
        if not data:
            return data

        allowed_keys = set(x_axis_keys + y_axis_keys)

        # Filter columns to only include those defined in axisConfig
        # Preserve original data order - do NOT sort, as the data source
        # is responsible for providing data in the correct order
        filtered_data = [
            {k: v for k, v in row.items() if k in allowed_keys} for row in data
        ]

        return filtered_data

    def _extract_ppt_title_override(
        self,
        hero_fields: Any,
        defined_markets: Optional[List[str]],
        automation_mode: Optional[str],
    ) -> Optional[str]:
        """Return a tier3/unattended PPT title from hero_fields.ppt_data, if present."""
        if not automation_mode or automation_mode.lower() not in {"tier3", "unattended"}:
            return None
        if not isinstance(hero_fields, dict):
            return None
        ppt_data = hero_fields.get("ppt_data")
        if not isinstance(ppt_data, list) or not ppt_data:
            return None

        target_market = None
        if defined_markets:
            for item in defined_markets:
                if isinstance(item, str) and item.strip():
                    target_market = item.strip()
                    break

        def _normalize(value: str) -> str:
            return value.strip().lower()

        if target_market:
            target_norm = _normalize(target_market)
            for entry in ppt_data:
                if not isinstance(entry, dict):
                    continue
                entry_market = entry.get("market") or entry.get("marketKey")
                if isinstance(entry_market, str) and _normalize(entry_market) == target_norm:
                    title = entry.get("title")
                    if isinstance(title, str) and title.strip():
                        return title.strip()

        for entry in ppt_data:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()

        return None

    def extract_presentation_metadata(
        self, json_data: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Extract presentation metadata from new JSON format
        """
        report = json_data.get("report", {})

        # Extract market name from defined_markets array
        defined_markets = report.get("defined_markets", [])
        if defined_markets and len(defined_markets) > 0:
            # Take first market and clean up (e.g., "Kansas City Industrial" → "Kansas City")
            market_full = defined_markets[0]
            # Remove property type suffix if present
            property_type = report.get("property_type", "Industrial")
            market_name = market_full.replace(property_type, "").strip()
        else:
            # Fallback: try to derive from report name or use default
            market_name = report.get("division", "Market")

        # Extract sector/property type
        sector_type = report.get("property_type", "Industrial")

        # Extract quarter
        quarter = report.get("quarter", "Q3 2024")

        # Header prefix - derive from division or publishing group if available
        header_prefix = report.get("division", "Figures")
        if not header_prefix or header_prefix == market_name:
            # Fallback to publishing group or generic default
            header_prefix = report.get("publishing_group", "Market Analysis")

        # Extract property sub-type and geography selections for title computation
        property_sub_type = report.get("property_sub_type", "Figures")

        # Extract geography selections for dynamic title generation
        vacancy_index = report.get("vacancy_index") or []
        submarket = report.get("submarket") or []
        district = report.get("district") or []

        # Get first non-empty value from each list
        vacancy_index_choice = vacancy_index[0] if vacancy_index else "All"
        submarket_choice = submarket[0] if submarket else "All"
        district_choice = district[0] if district else "All"

        computed_title = self._compute_report_title(
            property_sub_type=property_sub_type,
            default_title=report.get("name", "Market Report"),
            market_name=market_name,
            sector_type=sector_type,
            vacancy_index_choice=vacancy_index_choice,
            submarket_choice=submarket_choice,
            district_choice=district_choice,
        )

        hero_fields = report.get("hero_fields")
        ppt_title_override = self._extract_ppt_title_override(
            hero_fields=hero_fields,
            defined_markets=defined_markets,
            automation_mode=report.get("automation_mode"),
        )
        if ppt_title_override:
            computed_title = ppt_title_override

        publishing_group = report.get("publishing_group")
        asking_rate_type = report.get("asking_rate_type")
        asking_rate_frequency = report.get("asking_rate_frequency")
        absorption_calculation = report.get("absorption_calculation")
        total_vs_direct_absorption = report.get("total_vs_direct_absorption")

        return {
            "title": computed_title,
            "author": "CBRE Research",
            "property_type": sector_type,
            "property_sub_type": property_sub_type,
            "quarter": quarter,
            "template_name": report.get("template_name", ""),
            "header_prefix": header_prefix,  # e.g., "Midwest" or "Market Analysis"
            "market_name": market_name,  # e.g., "Kansas City"
            "sector_type": sector_type,  # e.g., "Industrial"
            "hero_fields": hero_fields,  # Hero fields for stats population,
            "defined_markets": defined_markets,
            "publishing_group": publishing_group,
            "asking_rate_type": asking_rate_type,
            "asking_rate_frequency": asking_rate_frequency,
            "absorption_calculation": absorption_calculation,
            "total_vs_direct_absorption": total_vs_direct_absorption,
        }

    def _compute_report_title(
        self,
        property_sub_type: Optional[str],
        default_title: str,
        market_name: str,
        sector_type: str,
        vacancy_index_choice: str = "All",
        submarket_choice: str = "All",
        district_choice: str = "All",
    ) -> str:
        """Return presentation title using config-driven strategy.

        Supported strategies (from template_config.py):
        - default: Use the report's default_title
        - format: Use template with {market_name}, {sector_type} placeholders
        - geography: Dynamic title based on selected geography (district > submarket > vacancy_index)
        """
        strategy = get_title_strategy(property_sub_type)
        mode = strategy.get("strategy", "default")

        if mode == "geography":
            # Geography-based dynamic title using patterns from config
            geography_patterns = strategy.get("geography_patterns", {})
            geography_values = {
                "district": district_choice,
                "submarket": submarket_choice,
                "vacancy_index": vacancy_index_choice,
            }

            # Check each geography in priority order (config order determines priority)
            for geo_type, pattern in geography_patterns.items():
                value = geography_values.get(geo_type, "All")
                if value and value.lower() != "all":
                    return pattern.format(value=value.title())

            # Fallback to default template if no geography selected
            default_template = strategy.get(
                "default_template", "{market_name} {sector_type} Snapshot"
            )
            return (
                default_template.format(
                    market_name=(market_name or "").strip(),
                    sector_type=(sector_type or "").strip(),
                ).strip()
                or default_title
            )

        if mode == "format":
            template = strategy.get("template", "{market_name} {sector_type} Snapshot")
            return (
                template.format(
                    market_name=(market_name or "").strip(),
                    sector_type=(sector_type or "").strip(),
                ).strip()
                or default_title
            )

        if mode == "literal":
            return strategy.get("value", default_title)

        return default_title

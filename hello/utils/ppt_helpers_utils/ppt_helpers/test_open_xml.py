"""
PowerPoint Chart and Table Cloner using OpenXML SDK approach

This uses direct ZIP/XML manipulation with proper relationship management
to clone charts and tables with exact styling preserved.

TABLE STYLES:
-------------
PowerPoint tables can have custom styles defined in ppt/tableStyles/ directory.
These styles are:
1. Automatically copied when using clone_shape_with_styles()
2. Shared across all tables in the presentation
3. Registered in [Content_Types].xml

Common table style files:
- tableStyleList.xml: Defines available table styles
- tableStyle1.xml, tableStyle2.xml, etc.: Individual style definitions

The cloner automatically:
✓ Copies all table style files from template
✓ Updates [Content_Types].xml
✓ Preserves relationships
✓ Maintains style references in cloned tables
"""

import zipfile
import os
import shutil
from lxml import etree
from copy import deepcopy
import re


class OpenXMLChartCloner:
    """
    Clone PowerPoint charts using OpenXML SDK approach.
    Properly handles all relationships and embedded files.
    """

    def __init__(self, template_path, temp_dir=None):
        self.template_path = template_path

        # Use provided temp_dir or default to /app/data/output_ppt
        if temp_dir is None:
            temp_dir = os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "data", "output_ppt"
            )
            temp_dir = os.path.abspath(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)
        self.temp_dir = temp_dir

        # XML namespaces
        self.nsmap = {
            "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
            "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
        }

    def clone_chart(
        self,
        target_path,
        output_path,
        template_slide_idx=0,
        target_slide_idx=0,
        left=None,
        top=None,
        width=None,
        height=None,
    ):
        """
        Clone chart from template to target presentation.

        Args:
            target_path: Path to target PowerPoint file
            output_path: Path for output file
            template_slide_idx: Template slide index (0-based)
            target_slide_idx: Target slide index (0-based)
            left/top/width/height: Position in EMUs (914400 EMUs = 1 inch)

        Returns:
            True if successful, False otherwise
        """
        temp_template_dir = None
        temp_target_dir = None

        try:
            # Extract both presentations
            temp_template_dir = os.path.join(self.temp_dir, "temp_template_extract")
            temp_target_dir = os.path.join(self.temp_dir, "temp_target_extract")

            print("Extracting presentations...")
            self._extract_zip(self.template_path, temp_template_dir)
            self._extract_zip(target_path, temp_target_dir)

            # Find chart in template
            print("Finding chart in template...")
            template_slide_path = f"ppt/slides/slide{template_slide_idx + 1}.xml"
            chart_info = self._find_chart_in_slide(
                temp_template_dir, template_slide_path
            )

            if not chart_info:
                raise ValueError(
                    f"No chart found in template slide {template_slide_idx}"
                )

            print(f"Found chart: {chart_info['chart_id']}")

            # Get next available IDs in target
            next_chart_num = self._get_next_chart_number(temp_target_dir)
            next_embed_num = self._get_next_embedding_number(temp_target_dir)

            print(f"Next chart number: {next_chart_num}")
            print(f"Next embedding number: {next_embed_num}")

            # Copy chart files with new IDs
            print("Copying chart files...")
            target_slide_path = f"ppt/slides/slide{target_slide_idx + 1}.xml"
            rel_id = self._copy_chart_files(
                temp_template_dir,
                temp_target_dir,
                chart_info,
                next_chart_num,
                next_embed_num,
                target_slide_path,
            )

            # Add chart shape to target slide
            print("Adding chart to target slide...")
            self._add_chart_to_slide(
                temp_target_dir,
                target_slide_path,
                chart_info,
                rel_id,
                next_chart_num,
                left,
                top,
                width,
                height,
            )

            # Update content types
            print("Updating content types...")
            self._update_content_types(temp_target_dir, next_chart_num)

            # Repackage as PPTX
            print("Creating output file...")
            self._create_zip(temp_target_dir, output_path)

            print(f"✓ Chart cloned successfully to: {output_path}")
            return True

        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback

            traceback.print_exc()
            return False

        finally:
            # Cleanup
            if temp_template_dir and os.path.exists(temp_template_dir):
                shutil.rmtree(temp_template_dir)
            if temp_target_dir and os.path.exists(temp_target_dir):
                shutil.rmtree(temp_target_dir)

    def clone_table(
        self,
        target_path,
        output_path,
        template_slide_idx=0,
        target_slide_idx=0,
        left=None,
        top=None,
        width=None,
        height=None,
    ):
        """
        Clone table from template to target presentation.

        Args:
            target_path: Path to target PowerPoint file
            output_path: Path for output file
            template_slide_idx: Template slide index (0-based)
            target_slide_idx: Target slide index (0-based)
            left/top/width/height: Position in EMUs (914400 EMUs = 1 inch)

        Returns:
            True if successful, False otherwise
        """
        temp_template_dir = None
        temp_target_dir = None

        try:
            # Extract both presentations
            temp_template_dir = os.path.join(
                self.temp_dir, "temp_template_extract_table"
            )
            temp_target_dir = os.path.join(self.temp_dir, "temp_target_extract_table")

            print("Extracting presentations...")
            self._extract_zip(self.template_path, temp_template_dir)
            self._extract_zip(target_path, temp_target_dir)

            # Find table in template
            print("Finding table in template...")
            template_slide_path = f"ppt/slides/slide{template_slide_idx + 1}.xml"
            table_info = self._find_table_in_slide(
                temp_template_dir, template_slide_path
            )

            if not table_info:
                raise ValueError(
                    f"No table found in template slide {template_slide_idx}"
                )

            print("Found table!")

            # Copy table styles (if they exist)
            print("Copying table styles...")
            self._copy_table_styles(temp_template_dir, temp_target_dir)

            # Add table to target slide
            print("Adding table to target slide...")
            target_slide_path = f"ppt/slides/slide{target_slide_idx + 1}.xml"
            self._add_table_to_slide(
                temp_target_dir, target_slide_path, table_info, left, top, width, height
            )

            # Repackage as PPTX
            print("Creating output file...")
            self._create_zip(temp_target_dir, output_path)

            print(f"✓ Table cloned successfully to: {output_path}")
            return True

        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback

            traceback.print_exc()
            return False

        finally:
            # Cleanup
            if temp_template_dir and os.path.exists(temp_template_dir):
                shutil.rmtree(temp_template_dir)
            if temp_target_dir and os.path.exists(temp_target_dir):
                shutil.rmtree(temp_target_dir)

    def _extract_zip(self, zip_path, extract_to):
        """Extract PPTX (which is a ZIP) to directory."""
        os.makedirs(extract_to, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_to)

    def _create_zip(self, folder_path, output_path):
        """Create PPTX from directory."""
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, folder_path)
                    zipf.write(file_path, arcname)

    def _find_chart_in_slide(self, pptx_dir, slide_path):
        """Find chart shape in slide and extract its info."""
        slide_file = os.path.join(pptx_dir, slide_path)

        if not os.path.exists(slide_file):
            return None

        tree = etree.parse(slide_file)
        root = tree.getroot()

        # Find graphicFrame with chart - use full namespace URIs
        graphic_frames = root.findall(
            ".//{http://schemas.openxmlformats.org/presentationml/2006/main}graphicFrame"
        )

        for graphic_frame in graphic_frames:
            # Check if it has a chart (nested in a:graphic/a:graphicData)
            chart_ref = graphic_frame.find(
                ".//{http://schemas.openxmlformats.org/drawingml/2006/chart}chart"
            )

            if chart_ref is not None:
                # Get relationship ID
                rel_id = chart_ref.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )

                # Get the chart file from relationships
                # Extract slide number properly using regex
                match = re.search(r"slide(\d+)", slide_path)
                if not match:
                    continue
                slide_num = match.group(1)
                rels_file = os.path.join(
                    pptx_dir, f"ppt/slides/_rels/slide{slide_num}.xml.rels"
                )

                if os.path.exists(rels_file):
                    rels_tree = etree.parse(rels_file)
                    for rel in rels_tree.findall(
                        ".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
                    ):
                        if rel.get("Id") == rel_id:
                            chart_target = rel.get("Target")
                            # Extract chart number properly using regex
                            chart_match = re.search(r"chart(\d+)", chart_target)
                            if not chart_match:
                                continue
                            chart_id = chart_match.group(1)

                            return {
                                "graphic_frame": graphic_frame,
                                "rel_id": rel_id,
                                "chart_id": chart_id,
                                "chart_target": chart_target,
                            }

        return None

    def _find_table_in_slide(self, pptx_dir, slide_path):
        """Find table in slide and extract its info."""
        slide_file = os.path.join(pptx_dir, slide_path)

        if not os.path.exists(slide_file):
            return None

        tree = etree.parse(slide_file)
        root = tree.getroot()

        # Find graphicFrame with table - use full namespace URIs
        for graphic_frame in root.findall(
            ".//{http://schemas.openxmlformats.org/presentationml/2006/main}graphicFrame"
        ):
            # Check if it has a table (nested in a:graphic/a:graphicData with table URI)
            graphic_data = graphic_frame.find(
                ".//{http://schemas.openxmlformats.org/drawingml/2006/main}graphicData"
            )
            if graphic_data is not None:
                uri = graphic_data.get("uri")
                if uri == "http://schemas.openxmlformats.org/drawingml/2006/table":
                    # Found a table!
                    table_elem = graphic_data.find(
                        ".//{http://schemas.openxmlformats.org/drawingml/2006/main}tbl"
                    )
                    if table_elem is not None:
                        return {
                            "graphic_frame": graphic_frame,
                            "table_elem": table_elem,
                            "type": "table",
                        }

        return None

    def _get_next_chart_number(self, pptx_dir):
        """Find next available chart number."""
        charts_dir = os.path.join(pptx_dir, "ppt/charts")
        max_num = 0

        if os.path.exists(charts_dir):
            for filename in os.listdir(charts_dir):
                match = re.match(r"chart(\d+)\.xml", filename)
                if match:
                    num = int(match.group(1))
                    max_num = max(max_num, num)

        return max_num + 1

    def _get_next_embedding_number(self, pptx_dir):
        """Find next available embedding number."""
        embed_dir = os.path.join(pptx_dir, "ppt/embeddings")
        max_num = 0

        if os.path.exists(embed_dir):
            for filename in os.listdir(embed_dir):
                match = re.match(r"Microsoft_Excel_Worksheet(\d+)\.xlsx", filename)
                if match:
                    num = int(match.group(1))
                    max_num = max(max_num, num)

        return max_num + 1

    def _copy_chart_files(
        self,
        src_dir,
        dst_dir,
        chart_info,
        new_chart_num,
        new_embed_num,
        target_slide_path,
    ):
        """Copy chart XML and embedded Excel files with new IDs."""

        # Source paths
        src_chart = os.path.join(
            src_dir, f"ppt/charts/chart{chart_info['chart_id']}.xml"
        )
        src_chart_rels = os.path.join(
            src_dir, f"ppt/charts/_rels/chart{chart_info['chart_id']}.xml.rels"
        )

        # Destination paths
        dst_chart = os.path.join(dst_dir, f"ppt/charts/chart{new_chart_num}.xml")
        dst_chart_rels = os.path.join(
            dst_dir, f"ppt/charts/_rels/chart{new_chart_num}.xml.rels"
        )

        # Create directories
        os.makedirs(os.path.join(dst_dir, "ppt/charts"), exist_ok=True)
        os.makedirs(os.path.join(dst_dir, "ppt/charts/_rels"), exist_ok=True)

        # Copy chart XML
        shutil.copy2(src_chart, dst_chart)

        # Copy and update chart relationships
        if os.path.exists(src_chart_rels):
            rels_tree = etree.parse(src_chart_rels)
            rels_root = rels_tree.getroot()

            # Copy all related files referenced in chart relationships
            for rel in rels_root.findall(".//rel:Relationship", self.nsmap):
                target = rel.get("Target")

                # Copy style and color XML files (e.g., style1.xml, colors1.xml)
                if target and not target.startswith(".."):
                    # It's a file in the same directory (charts/)
                    src_related = os.path.join(src_dir, f"ppt/charts/{target}")

                    # Rename style/color files to be unique per chart
                    # style1.xml -> style{new_chart_num}.xml
                    # colors1.xml -> colors{new_chart_num}.xml
                    new_filename = target
                    if "style" in target.lower() or "color" in target.lower():
                        # Extract base name and extension
                        base_name = target.rsplit(".", 1)[
                            0
                        ]  # e.g., "style1" or "colors1"
                        extension = target.rsplit(".", 1)[1]  # e.g., "xml"
                        # Remove any trailing numbers and add new chart number
                        base_name = re.sub(
                            r"\d+$", "", base_name
                        )  # "style1" -> "style"
                        new_filename = f"{base_name}{new_chart_num}.{extension}"

                        # Update the relationship to point to the new filename
                        rel.set("Target", new_filename)

                    dst_related = os.path.join(dst_dir, f"ppt/charts/{new_filename}")

                    if os.path.exists(src_related):
                        shutil.copy2(src_related, dst_related)
                        # Add to content types if it's an XML file
                        if new_filename.endswith(".xml"):
                            self._add_chart_style_to_content_types(
                                dst_dir, new_filename
                            )

                # Handle embeddings
                if "embeddings" in target:
                    # Copy embedding file
                    old_embed_file = os.path.basename(target)
                    new_embed_file = f"Microsoft_Excel_Worksheet{new_embed_num}.xlsx"

                    src_embed = os.path.join(
                        src_dir, f"ppt/embeddings/{old_embed_file}"
                    )
                    dst_embed = os.path.join(
                        dst_dir, f"ppt/embeddings/{new_embed_file}"
                    )

                    os.makedirs(os.path.join(dst_dir, "ppt/embeddings"), exist_ok=True)

                    if os.path.exists(src_embed):
                        shutil.copy2(src_embed, dst_embed)

                        # Update relationship target
                        rel.set("Target", f"../embeddings/{new_embed_file}")

                        # Add to content types
                        self._add_embedding_to_content_types(dst_dir, new_embed_file)

            # Save updated relationships
            rels_tree.write(
                dst_chart_rels,
                xml_declaration=True,
                encoding="UTF-8",
                pretty_print=True,
            )

        # Create new relationship in target slide and return its ID
        return self._get_next_rel_id(dst_dir, target_slide_path)

    def _get_next_rel_id(self, pptx_dir, slide_path):
        """Get next available relationship ID for a slide."""
        slide_num = "1"
        if "slide" in slide_path:
            match = re.search(r"slide(\d+)", slide_path)
            if match:
                slide_num = match.group(1)

        rels_file = os.path.join(
            pptx_dir, f"ppt/slides/_rels/slide{slide_num}.xml.rels"
        )

        max_id = 0
        if os.path.exists(rels_file):
            tree = etree.parse(rels_file)
            for rel in tree.findall(".//rel:Relationship", self.nsmap):
                rel_id = rel.get("Id")
                if rel_id and rel_id.startswith("rId"):
                    num = int(rel_id[3:])
                    max_id = max(max_id, num)

        return f"rId{max_id + 1}"

    def _add_chart_to_slide(
        self,
        pptx_dir,
        slide_path,
        chart_info,
        rel_id,
        chart_num,
        left,
        top,
        width,
        height,
    ):
        """Add chart graphic frame to target slide."""
        slide_file = os.path.join(pptx_dir, slide_path)

        if not os.path.exists(slide_file):
            raise ValueError(f"Target slide not found: {slide_path}")

        tree = etree.parse(slide_file)
        root = tree.getroot()

        # Clone the graphic frame
        new_frame = deepcopy(chart_info["graphic_frame"])

        # Update the relationship ID
        chart_ref = new_frame.find(".//c:chart", self.nsmap)
        if chart_ref is not None:
            chart_ref.set("{%s}id" % self.nsmap["r"], rel_id)

        # Update position/size if specified
        if any([left, top, width, height]):
            xfrm = new_frame.find(".//p:xfrm", self.nsmap)
            if xfrm is not None:
                off = xfrm.find("a:off", self.nsmap)
                ext = xfrm.find("a:ext", self.nsmap)

                if off is not None and left is not None:
                    off.set("x", str(int(left)))
                if off is not None and top is not None:
                    off.set("y", str(int(top)))
                if ext is not None and width is not None:
                    ext.set("cx", str(int(width)))
                if ext is not None and height is not None:
                    ext.set("cy", str(int(height)))

        # Add to slide's spTree
        sp_tree = root.find(".//p:spTree", self.nsmap)
        if sp_tree is not None:
            sp_tree.append(new_frame)

        # Save slide
        tree.write(
            slide_file, xml_declaration=True, encoding="UTF-8", pretty_print=True
        )

        # Add relationship
        self._add_slide_relationship(pptx_dir, slide_path, rel_id, chart_num)

    def _add_table_to_slide(
        self, pptx_dir, slide_path, table_info, left, top, width, height
    ):
        """Add table graphic frame to target slide."""
        slide_file = os.path.join(pptx_dir, slide_path)

        if not os.path.exists(slide_file):
            raise ValueError(f"Target slide not found: {slide_path}")

        tree = etree.parse(slide_file)
        root = tree.getroot()

        # Clone the graphic frame with table
        new_frame = deepcopy(table_info["graphic_frame"])

        # Update position/size if specified
        if any([left, top, width, height]):
            xfrm = new_frame.find(
                ".//{http://schemas.openxmlformats.org/presentationml/2006/main}xfrm"
            )
            if xfrm is not None:
                off = xfrm.find(
                    "{http://schemas.openxmlformats.org/drawingml/2006/main}off"
                )
                ext = xfrm.find(
                    "{http://schemas.openxmlformats.org/drawingml/2006/main}ext"
                )

                if off is not None and left is not None:
                    off.set("x", str(int(left)))
                if off is not None and top is not None:
                    off.set("y", str(int(top)))
                if ext is not None and width is not None:
                    ext.set("cx", str(int(width)))
                if ext is not None and height is not None:
                    ext.set("cy", str(int(height)))

        # Add to slide's spTree
        sp_tree = root.find(
            ".//{http://schemas.openxmlformats.org/presentationml/2006/main}spTree"
        )
        if sp_tree is not None:
            sp_tree.append(new_frame)

        # Save slide
        tree.write(
            slide_file, xml_declaration=True, encoding="UTF-8", pretty_print=True
        )

    def _add_slide_relationship(self, pptx_dir, slide_path, rel_id, chart_num):
        """Add chart relationship to slide's .rels file."""
        # Extract slide number using regex
        match = re.search(r"slide(\d+)", slide_path)
        slide_num = match.group(1) if match else "1"
        rels_file = os.path.join(
            pptx_dir, f"ppt/slides/_rels/slide{slide_num}.xml.rels"
        )

        # Create rels directory if needed
        os.makedirs(os.path.dirname(rels_file), exist_ok=True)

        # Load or create relationships file
        if os.path.exists(rels_file):
            tree = etree.parse(rels_file)
            root = tree.getroot()
        else:
            root = etree.Element(
                "{%s}Relationships" % self.nsmap["rel"], nsmap={None: self.nsmap["rel"]}
            )
            tree = etree.ElementTree(root)

        # Add new relationship
        rel = etree.SubElement(root, "{%s}Relationship" % self.nsmap["rel"])
        rel.set("Id", rel_id)
        rel.set(
            "Type",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart",
        )
        rel.set("Target", f"../charts/chart{chart_num}.xml")

        # Save
        tree.write(rels_file, xml_declaration=True, encoding="UTF-8", pretty_print=True)

    def _add_embedding_to_content_types(self, pptx_dir, embed_filename):
        """Add embedding to [Content_Types].xml."""
        content_types_file = os.path.join(pptx_dir, "[Content_Types].xml")

        if not os.path.exists(content_types_file):
            return

        tree = etree.parse(content_types_file)
        root = tree.getroot()

        part_name = f"/ppt/embeddings/{embed_filename}"

        # Check if exists
        for override in root.findall(
            ".//{http://schemas.openxmlformats.org/package/2006/content-types}Override"
        ):
            if override.get("PartName") == part_name:
                return

        # Add new override
        override = etree.SubElement(
            root,
            "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
        )
        override.set("PartName", part_name)
        override.set(
            "ContentType",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        tree.write(
            content_types_file,
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )

    def _add_chart_style_to_content_types(self, pptx_dir, style_filename):
        """Add chart style/color files to [Content_Types].xml."""
        content_types_file = os.path.join(pptx_dir, "[Content_Types].xml")

        if not os.path.exists(content_types_file):
            return

        tree = etree.parse(content_types_file)
        root = tree.getroot()

        part_name = f"/ppt/charts/{style_filename}"

        # Check if exists
        for override in root.findall(
            ".//{http://schemas.openxmlformats.org/package/2006/content-types}Override"
        ):
            if override.get("PartName") == part_name:
                return

        # Determine content type based on filename
        if "style" in style_filename.lower():
            content_type = "application/vnd.ms-office.chartstyle+xml"
        elif "color" in style_filename.lower():
            content_type = "application/vnd.ms-office.chartcolorstyle+xml"
        else:
            # Generic XML content type
            content_type = "application/xml"

        # Add new override
        override = etree.SubElement(
            root,
            "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
        )
        override.set("PartName", part_name)
        override.set("ContentType", content_type)

        tree.write(
            content_types_file,
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )

    def _update_content_types(self, pptx_dir, chart_num):
        """Update [Content_Types].xml for new chart."""
        content_types_file = os.path.join(pptx_dir, "[Content_Types].xml")

        if not os.path.exists(content_types_file):
            return

        tree = etree.parse(content_types_file)
        root = tree.getroot()

        part_name = f"/ppt/charts/chart{chart_num}.xml"

        # Check if exists
        for override in root.findall(
            ".//{http://schemas.openxmlformats.org/package/2006/content-types}Override"
        ):
            if override.get("PartName") == part_name:
                return

        # Add new override
        override = etree.SubElement(
            root,
            "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
        )
        override.set("PartName", part_name)
        override.set(
            "ContentType",
            "application/vnd.openxmlformats-officedocument.drawingml.chart+xml",
        )

        tree.write(
            content_types_file,
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )

    def _copy_table_styles(self, src_dir, dst_dir):
        """Copy table styles directory if it exists."""
        src_table_styles = os.path.join(src_dir, "ppt/tableStyles")
        dst_table_styles = os.path.join(dst_dir, "ppt/tableStyles")

        if not os.path.exists(src_table_styles):
            return

        # Create destination directory
        os.makedirs(dst_table_styles, exist_ok=True)

        # Copy all table style files
        for item in os.listdir(src_table_styles):
            src_item = os.path.join(src_table_styles, item)
            dst_item = os.path.join(dst_table_styles, item)

            if os.path.isfile(src_item):
                shutil.copy2(src_item, dst_item)

                # Add to content types
                if item.endswith(".xml"):
                    self._add_table_style_to_content_types(dst_dir, item)
            elif os.path.isdir(src_item):
                # Copy subdirectories (like _rels)
                if os.path.exists(dst_item):
                    shutil.rmtree(dst_item)
                shutil.copytree(src_item, dst_item)

    def _add_table_style_to_content_types(self, pptx_dir, style_filename):
        """Add table style files to [Content_Types].xml."""
        content_types_file = os.path.join(pptx_dir, "[Content_Types].xml")

        if not os.path.exists(content_types_file):
            return

        tree = etree.parse(content_types_file)
        root = tree.getroot()

        part_name = f"/ppt/tableStyles/{style_filename}"

        # Check if exists
        for override in root.findall(
            ".//{http://schemas.openxmlformats.org/package/2006/content-types}Override"
        ):
            if override.get("PartName") == part_name:
                return

        # Add new override
        override = etree.SubElement(
            root,
            "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
        )
        override.set("PartName", part_name)
        override.set(
            "ContentType",
            "application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml",
        )

        tree.write(
            content_types_file,
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )

    def clone_shape_with_styles(
        self,
        target_path,
        output_path,
        template_slide_idx=0,
        target_slide_idx=0,
        shape_type="chart",
        left=None,
        top=None,
        width=None,
        height=None,
    ):
        """
        Clone any shape (chart, table, etc.) from template to target with all styles.

        Args:
            target_path: Path to target PowerPoint file
            output_path: Path for output file
            template_slide_idx: Template slide index (0-based)
            target_slide_idx: Target slide index (0-based)
            shape_type: Type of shape to clone ('chart', 'table', or 'all')
            left/top/width/height: Position in EMUs (914400 EMUs = 1 inch)

        Returns:
            True if successful, False otherwise
        """
        temp_template_dir = None
        temp_target_dir = None

        try:
            # Extract both presentations
            temp_template_dir = os.path.join(self.temp_dir, "temp_template_extract")
            temp_target_dir = os.path.join(self.temp_dir, "temp_target_extract")

            print("Extracting presentations...")
            self._extract_zip(self.template_path, temp_template_dir)
            self._extract_zip(target_path, temp_target_dir)

            # Copy table styles from template to target (if they exist)
            print("Copying table styles...")
            self._copy_table_styles(temp_template_dir, temp_target_dir)

            # Now proceed with chart cloning as usual
            if shape_type in ["chart", "all"]:
                # Find chart in template
                print("Finding chart in template...")
                template_slide_path = f"ppt/slides/slide{template_slide_idx + 1}.xml"
                chart_info = self._find_chart_in_slide(
                    temp_template_dir, template_slide_path
                )

                if chart_info:
                    print(f"Found chart: {chart_info['chart_id']}")

                    # Get next available IDs in target
                    next_chart_num = self._get_next_chart_number(temp_target_dir)
                    next_embed_num = self._get_next_embedding_number(temp_target_dir)

                    print(f"Next chart number: {next_chart_num}")
                    print(f"Next embedding number: {next_embed_num}")

                    # Copy chart files with new IDs
                    print("Copying chart files...")
                    target_slide_path = f"ppt/slides/slide{target_slide_idx + 1}.xml"
                    rel_id = self._copy_chart_files(
                        temp_template_dir,
                        temp_target_dir,
                        chart_info,
                        next_chart_num,
                        next_embed_num,
                        target_slide_path,
                    )

                    # Add chart shape to target slide
                    print("Adding chart to target slide...")
                    self._add_chart_to_slide(
                        temp_target_dir,
                        target_slide_path,
                        chart_info,
                        rel_id,
                        next_chart_num,
                        left,
                        top,
                        width,
                        height,
                    )

                    # Update content types
                    print("Updating content types...")
                    self._update_content_types(temp_target_dir, next_chart_num)

            # Repackage as PPTX
            print("Creating output file...")
            self._create_zip(temp_target_dir, output_path)

            print(f"✓ Shape cloned successfully to: {output_path}")
            return True

        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback

            traceback.print_exc()
            return False

        finally:
            # Cleanup
            if temp_template_dir and os.path.exists(temp_template_dir):
                shutil.rmtree(temp_template_dir)
            if temp_target_dir and os.path.exists(temp_target_dir):
                shutil.rmtree(temp_target_dir)


# Convenience function
def clone_chart(
    template_path,
    target_path,
    output_path,
    template_slide_idx=0,
    target_slide_idx=0,
    left_inches=None,
    top_inches=None,
    width_inches=None,
    height_inches=None,
):
    """
    Clone chart from template to target presentation.

    Args:
        template_path: Path to template with chart
        target_path: Path to target presentation
        output_path: Path for output file
        template_slide_idx: Template slide index (0-based)
        target_slide_idx: Target slide index (0-based)
        left_inches/top_inches/width_inches/height_inches: Position in inches

    Returns:
        True if successful
    """
    # Convert inches to EMUs (914400 EMUs = 1 inch)
    left = int(left_inches * 914400) if left_inches else None
    top = int(top_inches * 914400) if top_inches else None
    width = int(width_inches * 914400) if width_inches else None
    height = int(height_inches * 914400) if height_inches else None

    cloner = OpenXMLChartCloner(template_path)
    return cloner.clone_chart(
        target_path,
        output_path,
        template_slide_idx,
        target_slide_idx,
        left,
        top,
        width,
        height,
    )


# Convenience function for tables
def clone_table(
    template_path,
    target_path,
    output_path,
    template_slide_idx=0,
    target_slide_idx=0,
    left_inches=None,
    top_inches=None,
    width_inches=None,
    height_inches=None,
):
    """
    Clone table from template to target presentation.

    Args:
        template_path: Path to template with table
        target_path: Path to target presentation
        output_path: Path for output file
        template_slide_idx: Template slide index (0-based)
        target_slide_idx: Target slide index (0-based)
        left_inches/top_inches/width_inches/height_inches: Position in inches

    Returns:
        True if successful
    """
    # Convert inches to EMUs (914400 EMUs = 1 inch)
    left = int(left_inches * 914400) if left_inches else None
    top = int(top_inches * 914400) if top_inches else None
    width = int(width_inches * 914400) if width_inches else None
    height = int(height_inches * 914400) if height_inches else None

    cloner = OpenXMLChartCloner(template_path)
    return cloner.clone_table(
        target_path,
        output_path,
        template_slide_idx,
        target_slide_idx,
        left,
        top,
        width,
        height,
    )


# # Example usage
# if __name__ == "__main__":
#     from pptx import Presentation

#     # Create a simple target presentation
#     print("Creating target presentation...")
#     target_prs = Presentation()
#     blank_layout = target_prs.slide_layouts[6]
#     slide = target_prs.slides.add_slide(blank_layout)
#     target_prs.save("my_presentation.pptx")

#     # Standard slide is 10" x 7.5"

#     # Clone FIRST chart - positioned in upper right corner
#     print("\n=== Cloning Chart 1: Asking Rents ===")
#     success1 = clone_chart(
#         template_path=r"/Users/utkarshgeda/Documents/Work/Turing/test_pptx_gen/templates/Asking Rents.pptx",
#         target_path="my_presentation.pptx",
#         output_path="temp_with_chart1.pptx",  # Temporary output
#         template_slide_idx=0,
#         target_slide_idx=0,
#         left_inches=5.5,    # Upper right corner
#         top_inches=0.5,
#         width_inches=4,
#         height_inches=3
#     )

#     if not success1:
#         print("\n✗ Failed to clone first chart")
#         exit(1)

#     # Clone SECOND chart - positioned in upper left corner
#     # Use the output from first clone as the target for second clone
#     print("\n=== Cloning Chart 2: Leasing Activity Trend ===")
#     success2 = clone_chart(
#         template_path=r"/Users/utkarshgeda/Documents/Work/Turing/test_pptx_gen/templates/Leasing Activity Trend.pptx",
#         target_path="temp_with_chart1.pptx",  # Use previous output as target
#         output_path="output_with_2_charts.pptx",  # Final output
#         template_slide_idx=0,
#         target_slide_idx=0,
#         left_inches=0.5,    # Upper left corner
#         top_inches=0.5,
#         width_inches=4,
#         height_inches=3
#     )

#     if not success2:
#         print("\n✗ Failed to clone second chart")
#         exit(1)

#     # Clone TABLE - positioned at bottom center
#     print("\n=== Cloning Table: Market Stats ===")
#     success3 = clone_table(
#         template_path=r"/Users/utkarshgeda/Documents/Work/Turing/test_pptx_gen/templates/table_Market_stats.pptx",
#         target_path="output_with_2_charts.pptx",  # Use previous output as target
#         output_path="output_with_2_charts_and_table.pptx",  # Final output
#         template_slide_idx=0,
#         target_slide_idx=0,
#         left_inches=1.5,    # Bottom center
#         top_inches=4.5,
#         width_inches=7,
#         height_inches=2.5
#     )

#     # Clean up temporary files
#     import os
#     if os.path.exists("temp_with_chart1.pptx"):
#         os.remove("temp_with_chart1.pptx")

#     if success1 and success2 and success3:
#         print("\n✓ Success! Check output_with_2_charts_and_table.pptx")
#         print("  - Chart 1 (Asking Rents): Upper right")
#         print("  - Chart 2 (Leasing Activity): Upper left")
#         print("  - Table (Market Stats): Bottom center")
#     else:
#         print("\n✗ Failed - check error messages above")

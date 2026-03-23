"""
PPT Generation Router

This router integrates the standalone PPT generation API from utils/api/
into the main CBRE application without modifying any existing logic.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import json
import os
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
import sys
import re

# Import the PPT generation logic from services
from app.ppt_engine.ppt_helpers_utils.services.frontend_json_processor import FrontendJSONProcessor
from app.ppt_engine.ppt_helpers_utils.services.presentation_generator import PresentationGenerator

# Setup directories for PPT generation
BACKEND_DIR = Path(__file__).parent.parent  # Points to src/hello
TEMPLATES_DIR = BACKEND_DIR / "utils"/"ppt_helpers_utils"/"individual_templates"  # Using chart-type-based templates
OUTPUT_DIR = BACKEND_DIR / "data"/"output_ppt"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Initialize components (module-level singletons for performance)
# Note: These are reused across multiple PPT generations. The PresentationGenerator
# properly resets renderer state at the start of each generation to ensure clean state
# for multi-market reports. See presentation_generator.py line ~88 for state reset logic.
json_processor = FrontendJSONProcessor(templates_dir=str(TEMPLATES_DIR))
presentation_generator = PresentationGenerator(output_dir=str(OUTPUT_DIR))

# In-memory storage for generated files
generated_files: Dict[str, Dict[str, Any]] = {}

router = APIRouter()

# ============================================================================
# Pydantic Models - Matching the standalone API schema
# ============================================================================

class ReportMetadata(BaseModel):
    """Report metadata from new JSON format"""
    model_config = {"extra": "allow"}  # Allow extra fields not defined in the model
    
    id: Optional[int] = Field(default=None, description="Report ID")
    name: str = Field(default="Market Report", description="Report name")
    template_id: Optional[int] = Field(default=None, description="Template ID")
    template_name: Optional[str] = Field(default=None, description="Template name")
    report_type: Optional[str] = Field(default=None, description="Report type")
    division: Optional[str] = Field(default=None, description="Division")
    publishing_group: Optional[str] = Field(default=None, description="Publishing group")
    property_type: str = Field(default="Industrial", description="Property type")
    property_sub_type: str = Field(default="Figures", description="Property sub-type")
    defined_markets: Optional[List[str]] = Field(default=None, description="Defined markets")
    quarter: Optional[str] = Field(default=None, description="Quarter (e.g., 2025 Q2)")
    history_range: Optional[str] = Field(default=None, description="History range")
    absorption_calculation: Optional[str] = Field(default=None, description="Absorption calculation")
    total_vs_direct_absorption: Optional[str] = Field(default=None, description="Total vs direct absorption")
    asking_rate_frequency: Optional[str] = Field(default=None, description="Asking rate frequency")
    asking_rate_type: Optional[str] = Field(default=None, description="Asking rate type")
    minimum_transaction_size: Optional[int] = Field(default=None, description="Minimum transaction size")
    use_auto_generated_text: Optional[bool] = Field(default=None, description="Use auto generated text")
    automation_mode: Optional[str] = Field(default=None, description="Automation mode")
    status: Optional[str] = Field(default=None, description="Status")
    created_at: Optional[str] = Field(default=None, description="Created at")
    updated_at: Optional[str] = Field(default=None, description="Updated at")
    hero_fields: Optional[dict[str, Any]] = Field(default=None, description="Hero Fields")


class PromptTemplate(BaseModel):
    """Prompt template configuration"""
    model_config = {"extra": "allow"}
    
    id: Optional[int] = None
    label: Optional[str] = None
    body: Optional[str] = None


class ElementConfig(BaseModel):
    """Element configuration"""
    model_config = {"extra": "allow"}  # Allow extra fields not defined in the model
    
    # Text/Commentary fields
    content: Optional[str] = None
    commentary_text: Optional[str] = None  # New format
    commentary_json: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    
    # KPI fields
    kpi_value: Optional[str] = None
    kpi_label: Optional[str] = None
    trend: Optional[str] = None
    
    # Chart fields
    chart_type: Optional[str] = None
    chart_data: Optional[List[Dict]] = None  # New format - embedded data
    chart_name: Optional[str] = None  # New format
    chart_label: Optional[str] = None  # New format
    chart_source: Optional[str] = None  # New format
    figure_name: Optional[str] = None
    figure_source: Optional[str] = None
    sql: Optional[str] = None
    sql_list: Optional[List[str]] = None
    
    # Table fields
    table_type: Optional[str] = None
    table_data: Optional[List[Dict]] = None  # New format - embedded data
    table_rows: Optional[str] = None
    table_columns: Optional[str] = None
    table_columns_sequence: Optional[List[str]] = None  # Column ordering sequence
    rows: Optional[int] = None
    columns: Optional[int] = None
    include_totals: Optional[bool] = None
    highlight_changes: Optional[bool] = None
    
    # Common fields
    type: Optional[str] = None
    name: Optional[str] = None
    label: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    section_name: Optional[str] = None
    property_type: Optional[str] = None
    property_sub_type: Optional[str] = None
    adjust_prompt: Optional[str] = None
    prompt_template_body: Optional[str] = None


class Element(BaseModel):
    """Section element"""
    model_config = {"extra": "allow"}  # Allow extra fields not defined in the model
    
    id: int = Field(description="Element ID")
    element_type: str = Field(description="Element type: chart, table, commentary, title, kpi, summary")
    label: Optional[str] = Field(default=None, description="Element label")
    selected: bool = Field(default=True, description="Whether element is selected")
    display_order: int = Field(default=0, description="Display order")
    config: ElementConfig = Field(description="Element configuration")
    section_commentary: Optional[str] = Field(default=None, description="Section commentary")
    prompt_text: Optional[str] = Field(default=None, description="Prompt text")


class Section(BaseModel):
    """Presentation section"""
    model_config = {"extra": "allow"}  # Allow extra fields not defined in the model
    
    id: Optional[int] = Field(default=None, description="Section ID")
    key: Optional[str] = Field(default=None, description="Section key")
    name: Optional[str] = Field(default=None, description="Section name")
    section_name: Optional[str] = Field(default=None, description="Section name (alternative)")
    display_order: Optional[int] = Field(default=None, description="Display order")
    selected: Optional[bool] = Field(default=True, description="Whether section is selected")
    prompt_template: Optional[PromptTemplate] = Field(default=None, description="Prompt template")
    commentary: Optional[str] = Field(default=None, description="Commentary")
    elements: List[Element] = Field(description="Section elements")
    charts_sql: Optional[List[str]] = Field(default=None, description="Chart SQL queries")
    tables_sql: Optional[List[str]] = Field(default=None, description="Table SQL queries")
    
    # Legacy fields for backward compatibility (if needed later)
    template_name: Optional[str] = Field(default=None)
    property_type: Optional[str] = Field(default=None)
    prompt_template_id: Optional[int] = Field(default=None)
    slide_number: Optional[int] = Field(default=None)
    layout_preference: Optional[str] = Field(default=None)
    charts: Optional[List[str]] = Field(default=None)
    tables: Optional[List[str]] = Field(default=None)
    charts_data: Optional[List[List[Dict]]] = Field(default=None, description="Chart data arrays")
    tables_data: Optional[List[List[Dict]]] = Field(default=None, description="Table data arrays")


class FrontendJSONRequest(BaseModel):
    """Complete frontend JSON request - New format"""
    model_config = {"extra": "allow"}  # Allow extra fields not defined in the model
    
    report: ReportMetadata = Field(description="Report metadata")
    sections: List[Section] = Field(description="Report sections")


class GenerationResponse(BaseModel):
    """Response model for generation"""
    success: bool
    message: str
    file_id: Optional[str] = None
    download_url: Optional[str] = None
    file_size: Optional[int] = None
    slides_generated: Optional[int] = None


class FileInfo(BaseModel):
    """File information model"""
    file_id: str
    filename: str
    title: str
    created_at: str
    file_size: int
    sections_count: int
    exists: bool


# ============================================================================
# API Endpoints
# ============================================================================


async def generate_presentation(
    request: FrontendJSONRequest | dict
):
    """
    Generate PowerPoint presentation from frontend JSON without blocking the event loop.
    """
    return await asyncio.to_thread(_generate_presentation_sync, request)


def _generate_presentation_sync(
    request: FrontendJSONRequest | dict
):
    """
    Synchronous implementation that performs the heavy PPT generation work.
    """
    try:
        file_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Handle both dict and Pydantic model inputs
        if isinstance(request, dict):
            json_data = request
            report_name = json_data.get('report', {}).get('name', 'Report')
            sections_count = len(json_data.get('sections', []))
        else:
            json_data = request.model_dump(mode='json', exclude_none=False, by_alias=False)
            report_name = request.report.name
            sections_count = len(request.sections)
        
        print(f"\n{'='*60}")
        print(f"🚀 Processing generation request")
        print(f"   File ID: {file_id}")
        print(f"   Title: {report_name}")
        print(f"   Sections: {sections_count}")
        print(f"{'='*60}\n")
        
        # Extract metadata
        metadata = json_processor.extract_presentation_metadata(json_data)
        print(f"📊 Presentation Metadata:")
        print(f"   Title: {metadata['title']}")
        print(f"   Author: {metadata['author']}")
        print(f"   Property Type: {metadata['property_type']}")
        if metadata.get('quarter'):
            print(f"   Quarter: {metadata['quarter']}")
        print()
        
        # Parse sections
        try:
            orch_sections = json_processor.parse_frontend_json(json_data)
            print(f"✅ Parsed {len(orch_sections)} sections successfully\n")
        except Exception as e:
            print(f"❌ Failed to parse sections: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to parse sections: {str(e)}")
        
        # Generate presentation (empty PPT will be created if no valid sections)
        # Format: report_name_template_type_quarter_timestamp.pptx
        template_type = metadata.get('property_sub_type', 'Figures')
        quarter = metadata.get('quarter', '')
        output_filename = f"{report_name}_{template_type}_{quarter}_{timestamp}.pptx"
        # Replace all non-alphanumeric characters (except dots for file extension) with underscores
        output_filename = re.sub(r'[^a-zA-Z0-9._]', '_', output_filename)
        
        try:
            print(f"🎨 Generating presentation...")
            output_path = presentation_generator.generate_presentation(
                sections=orch_sections,
                title=metadata['title'],
                author=metadata['author'],
                output_filename=output_filename,
                metadata=metadata
            )
            print(f"✅ Generated: {output_filename}\n")
        except Exception as e:
            print(f"❌ Generation failed: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Presentation generation failed: {str(e)}")
        
        # Verify file exists
        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="Generated file not found")
        
        # Store file information
        file_size = os.path.getsize(output_path)
        file_info = {
            "file_id": file_id,
            "file_path": output_path,
            "filename": output_filename,
            "created_at": datetime.now().isoformat(),
            "title": metadata['title'],
            "author": metadata['author'],
            "sections_count": sections_count
        }
        
        generated_files[file_id] = file_info
        
        return file_info
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# @router.get("/templates")
# async def list_templates():
#     """
#     List available PowerPoint templates
    
#     Returns:
#         List of available chart and table templates
#     """
#     if not TEMPLATES_DIR.exists():
#         return {"templates": [], "count": 0}
    
#     templates = []
#     for template_file in sorted(TEMPLATES_DIR.glob("*.pptx")):
#         template_name = template_file.stem
#         templates.append({
#             "filename": template_file.name,
#             "name": template_name.replace('_', ' ').title(),
#             "type": "table" if template_name.startswith("table_") else "chart",
#             "size": template_file.stat().st_size
#         })
    
#     return {
#         "templates": templates,
#         "count": len(templates),
#         "directory": str(TEMPLATES_DIR)
#     }

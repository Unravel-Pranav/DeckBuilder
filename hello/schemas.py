from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal, Dict, Any, List

from pydantic import BaseModel, Field, field_validator


_PPT_URL_SINGLE_ENTRY_KEYS = {"ppt_url", "pptUrl", "url", "link"}


def _normalize_ppt_url_entries(value: Any) -> list[dict[str, str]] | None:
    """Coerce legacy ppt_url payloads into a uniform list of {name, ppt_url}."""
    if value is None:
        return None

    # Already a sequence of values (list/tuple/InstrumentedList, etc.)
    if isinstance(value, (list, tuple)):
        entries: list[Any] = list(value)
    elif isinstance(value, BaseModel):
        entries = [value.model_dump()]
    elif isinstance(value, dict):
        # Dictionaries with explicit ppt_url fields represent a single entry.
        if any(key in value for key in _PPT_URL_SINGLE_ENTRY_KEYS):
            entries = [value]
        else:
            # Treat mapping of {name: url} as multiple entries.
            normalized_map: list[dict[str, str]] = []
            for idx, (name, url) in enumerate(value.items(), start=1):
                if not url:
                    continue
                normalized_map.append(
                    {
                        "name": str(name) if name else f"PPT {idx}",
                        "ppt_url": str(url),
                    }
                )
            return normalized_map
    else:
        entries = [value]

    normalized: list[dict[str, str]] = []
    for idx, entry in enumerate(entries, start=1):
        if entry is None:
            continue
        if isinstance(entry, BaseModel):
            entry = entry.model_dump()
        if isinstance(entry, str):
            candidate = entry.strip()
            if not candidate:
                continue
            normalized.append({"name": f"PPT {idx}", "ppt_url": candidate})
            continue
        if isinstance(entry, dict):
            url = (
                entry.get("ppt_url")
                or entry.get("pptUrl")
                or entry.get("url")
                or entry.get("link")
            )
            name = (
                entry.get("name")
                or entry.get("market")
                or entry.get("label")
                or entry.get("title")
            )
            if not url and len(entry) == 1:
                name, url = next(iter(entry.items()))
            if not url:
                continue
            normalized.append(
                {
                    "name": str(name) if name else f"PPT {idx}",
                    "ppt_url": str(url),
                }
            )
            continue
        if isinstance(entry, (list, tuple)):
            if not entry:
                continue
            url = entry[-1]
            name = entry[0] if len(entry) > 1 else None
            if not url:
                continue
            normalized.append(
                {
                    "name": str(name) if name else f"PPT {idx}",
                    "ppt_url": str(url),
                }
            )
            continue
        # Fallback: coerce to string representation.
        normalized.append({"name": f"PPT {idx}", "ppt_url": str(entry)})

    if normalized:
        return normalized
    if isinstance(value, (list, tuple)):
        return []
    return None


class UserIn(BaseModel):
    email: str
    username: str
    miq_user_id: Optional[int] = None


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    miq_user_id: Optional[int] = None

    class Config:
        from_attributes = True


# ==========================
# Scheduler runtime schemas
# ==========================


class JobScheduleIn(BaseModel):
    script_name: str
    endpoint: str
    method: str = "POST"
    payload: Optional[dict] = None
    headers: Optional[dict] = None
    enabled: bool = True
    next_run_at: datetime
    every_seconds: int


class JobScheduleUpdate(BaseModel):
    script_name: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    payload: Optional[dict] = None
    headers: Optional[dict] = None
    enabled: Optional[bool] = None
    next_run_at: Optional[datetime] = None
    every_seconds: Optional[int] = None


class JobScheduleOut(BaseModel):
    id: int
    script_name: str
    endpoint: str
    method: str
    payload: Optional[dict] = None
    headers: Optional[dict] = None
    enabled: bool
    next_run_at: datetime
    every_seconds: int
    updated_at: datetime

    class Config:
        from_attributes = True


class JobQueueOut(BaseModel):
    id: int
    script_name: str
    endpoint: str
    method: str
    payload: Optional[dict] = None
    headers: Optional[dict] = None
    run_at: datetime
    status: str
    attempts: int
    max_attempts: int
    last_error: Optional[str] = None
    response: Optional[dict] = None
    leased_by: Optional[str] = None
    lease_until: Optional[datetime] = None
    heartbeat_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LeaseRequest(BaseModel):
    batch_size: int = 5
    worker_id: str
    lease_seconds: int = 900


class RenewLeaseRequest(BaseModel):
    lease_seconds: int = 900


class CompleteJobRequest(BaseModel):
    response: Optional[dict] = None


class FailJobRequest(BaseModel):
    error: str
    backoff_seconds: int = 300


class RunNowRequest(BaseModel):
    schedule_id: Optional[int] = None
    # Optional ad-hoc parameters override schedule
    script_name: Optional[str] = None
    endpoint: Optional[str] = None
    method: str = "POST"
    payload: Optional[dict] = None
    headers: Optional[dict] = None


class UserUpdate(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    miq_user_id: Optional[int] = None


class TemplateSectionElementIn(BaseModel):
    element_type: Literal["chart", "table", "commentary"]
    display_order: int = 0
    config: dict = Field(default_factory=dict)


class TemplateSectionIn(BaseModel):
    name: str
    sectionname_alias: str
    label: Optional[str] = None
    property_type: str
    property_sub_type: Optional[str] = None
    tier: Optional[str] = None
    markets: Optional[str] = None
    division: Optional[str] = None
    publishing_group: Optional[str] = None
    automation_mode: Optional[str] = None
    quarter: Optional[str] = None
    history_range: Optional[str] = None
    absorption_calculation: Optional[str] = None
    total_vs_direct_absorption: Optional[str] = None
    asking_rate_frequency: Optional[str] = None
    asking_rate_type: Optional[str] = None
    minimum_transaction_size: Optional[int] = None
    use_auto_generated_text: Optional[bool] = None
    report_parameters: Optional[SectionReportParameters | dict] = None
    vacancy_index: Optional[list[str]] = None
    submarket: Optional[list[str]] = None
    district: Optional[list[str]] = None
    default_prompt: Optional[str] = None
    chart_config: Optional[dict] = None
    table_config: Optional[dict] = None
    slide_layout: Optional[str] = None
    mode: Optional[str] = None
    elements: Optional[list[TemplateSectionElementIn]] = None


class TemplateSectionElementOut(BaseModel):
    id: int
    section_id: int
    element_type: str
    display_order: int
    config: dict = Field(default_factory=dict)
    created_at: datetime

    class Config:
        from_attributes = True



class OptionListResponse(BaseModel):
    items: list[str] = Field(default_factory=list)


class SectionReportParameters(BaseModel):
    automation_mode: Optional[str] = None
    division: Optional[str] = None
    publishing_group: Optional[str] = None
    defined_markets: list[str] = Field(default_factory=list)
    quarter: Optional[str] = None
    history_range: Optional[str] = None
    absorption_calculation: Optional[str] = None
    total_vs_direct_absorption: Optional[str] = None
    asking_rate_frequency: Optional[str] = None
    asking_rate_type: Optional[str] = None
    minimum_transaction_size: Optional[int] = None
    use_auto_generated_text: Optional[bool] = None
    property_sub_type: Optional[str] = None
    vacancy_index: Optional[List[str]] = None
    submarket: Optional[List[str]] = None
    district: Optional[List[str]] = None


class TemplateRefOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class TemplateSectionOut(BaseModel):
    id: int
    name: str
    sectionname_alias: str
    label: Optional[str] = None
    prompt_template_id: Optional[int] = None
    prompt_template_label: Optional[str] = None
    prompt_template_body: Optional[str] = None
    property_type: str
    property_sub_type: Optional[str] = None
    tier: Optional[str] = None
    markets: Optional[str] = None
    division: Optional[str] = None
    publishing_group: Optional[str] = None
    automation_mode: Optional[str] = None
    quarter: Optional[str] = None
    history_range: Optional[str] = None
    absorption_calculation: Optional[str] = None
    total_vs_direct_absorption: Optional[str] = None
    asking_rate_frequency: Optional[str] = None
    asking_rate_type: Optional[str] = None
    minimum_transaction_size: Optional[int] = None
    use_auto_generated_text: Optional[bool] = None
    report_parameters: Optional[SectionReportParameters | dict] = None
    vacancy_index: Optional[list[str]] = None
    submarket: Optional[list[str]] = None
    district: Optional[list[str]] = None
    default_prompt: Optional[str] = None
    # Newly added persisted fields
    commentary: Optional[str] = None
    adjust_prompt: Optional[str] = None
    prompt_template: Optional[str] = None
    chart_config: Optional[dict] = None
    table_config: Optional[dict] = None
    slide_layout: Optional[str] = None
    mode: Optional[str] = None
    created_by_email: Optional[str] = None
    modified_by_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    template_id: Optional[int] = None
    template_ids: list[int] = Field(default_factory=list)
    templates: list[TemplateRefOut] = Field(default_factory=list)
    elements: list[TemplateSectionElementOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class TemplateSectionListResponse(BaseModel):
    totalCount: int
    items: list[TemplateSectionOut] = Field(default_factory=list)


class FinalizeSectionElementIn(BaseModel):
    type: Literal["chart", "table", "commentary"]
    order: int
    config: dict = Field(default_factory=dict)


class FinalizeTemplateRef(BaseModel):
    existing_template_id: Optional[int] = None
    new_template_name: Optional[str] = None
    base_type: Optional[str] = None
    is_default: bool = False
    attended: Optional[bool] = None


class FinalizeSectionPayload(BaseModel):
    existing_section_id: Optional[int] = None
    name: str
    sectionname_alias: str
    label: Optional[str] = None
    property_type: str
    property_sub_type: Optional[str] = None
    prompt_template: Optional[str] = None
    prompt_template_id: Optional[int] = None
    prompt_template_label: Optional[str] = None
    prompt_template_body: Optional[str] = None
    adjust_prompt: Optional[str] = None
    elements: list[FinalizeSectionElementIn] = Field(default_factory=list)


class FinalizeSectionRequest(BaseModel):
    template: FinalizeTemplateRef
    section: FinalizeSectionPayload
    report_parameters: Optional[SectionReportParameters] = None


class FinalizeSectionResponse(BaseModel):
    template: TemplateOut
    section: TemplateSectionOut


class TemplateSectionUpdate(BaseModel):
    name: Optional[str] = None
    sectionname_alias: Optional[str] = None
    label: Optional[str] = None
    property_type: Optional[str] = None
    property_sub_type: Optional[str] = None
    tier: Optional[str] = None
    markets: Optional[str] = None
    division: Optional[str] = None
    publishing_group: Optional[str] = None
    automation_mode: Optional[str] = None
    quarter: Optional[str] = None
    history_range: Optional[str] = None
    absorption_calculation: Optional[str] = None
    total_vs_direct_absorption: Optional[str] = None
    asking_rate_frequency: Optional[str] = None
    asking_rate_type: Optional[str] = None
    minimum_transaction_size: Optional[int] = None
    use_auto_generated_text: Optional[bool] = None
    report_parameters: Optional[SectionReportParameters | dict] = None
    vacancy_index: Optional[list[str]] = None
    submarket: Optional[list[str]] = None
    district: Optional[list[str]] = None
    default_prompt: Optional[str] = None
    chart_config: Optional[dict] = None
    table_config: Optional[dict] = None
    slide_layout: Optional[str] = None
    mode: Optional[str] = None
    elements: Optional[list[TemplateSectionElementIn]] = None


class SectionUpdate(BaseModel):
    sectionname_alias: Optional[str] = None
    label: Optional[str] = None
    property_type: Optional[str] = None
    property_sub_type: Optional[str] = None
    tier: Optional[str] = None
    markets: Optional[str] = None
    division: Optional[str] = None
    publishing_group: Optional[str] = None
    automation_mode: Optional[str] = None
    quarter: Optional[str] = None
    history_range: Optional[str] = None
    absorption_calculation: Optional[str] = None
    total_vs_direct_absorption: Optional[str] = None
    asking_rate_frequency: Optional[str] = None
    asking_rate_type: Optional[str] = None
    minimum_transaction_size: Optional[int] = None
    use_auto_generated_text: Optional[bool] = None
    report_parameters: Optional[SectionReportParameters | dict] = None
    default_prompt: Optional[str] = None
    commentary: Optional[str] = None
    adjust_prompt: Optional[str] = None
    prompt_template: Optional[str] = None
    chart_config: Optional[dict] = None
    table_config: Optional[dict] = None
    slide_layout: Optional[str] = None
    mode: Optional[str] = None
    elements: Optional[list[TemplateSectionElementIn]] = None


class TemplateIn(BaseModel):
    name: str
    base_type: str
    is_default: bool = False
    attended: bool = True
    ppt_status: str = "Not Attached"
    ppt_attached_time: datetime | None = None
    sections: list[TemplateSectionIn] = Field(default_factory=list)
    section_ids: list[int] = Field(default_factory=list)


class TemplateOut(BaseModel):
    id: int
    name: str
    base_type: str
    is_default: bool
    attended: bool
    ppt_status: str
    ppt_attached_time: datetime | None
    ppt_url: Optional[str] = None
    created_at: datetime
    last_modified: datetime
    created_by_email: Optional[str] = None
    modified_by_email: Optional[str] = None

    class Config:
        from_attributes = True


class TemplateListItemOut(TemplateOut):
    sections: Optional[list[TemplateSectionOut]] = None


class TemplateListResponse(BaseModel):
    totalCount: int
    items: list[TemplateListItemOut] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    base_type: Optional[str] = None
    is_default: Optional[bool] = None
    attended: Optional[bool] = None
    ppt_status: Optional[str] = None
    ppt_attached_time: Optional[datetime] = None
    sections: Optional[list[TemplateSectionIn]] = None


class TemplateDetailOut(TemplateOut):
    sections: list[TemplateSectionOut]


class PromptIn(BaseModel):
    section: str
    label: str
    body: str
    prompt_list: list[str] = []
    market: Optional[str] = None
    property_type: Optional[str] = None
    tier: Optional[str] = None
    status: str = "Active"
    is_default: bool = False
    # Note: 'author' field removed - use created_by tracking instead


class PromptOut(BaseModel):
    id: int
    section: str
    label: str
    version: int
    body: str
    prompt_list: list[str] = Field(default_factory=list)
    property_type: Optional[str] = None
    status: str
    created_at: datetime
    last_modified: datetime
    upvotes: int
    downvotes: int
    # Helpful extras for UI
    market: Optional[str] = None
    is_default: bool = False
    created_by_email: Optional[str] = None
    modified_by_email: Optional[str] = None
    # Note: 'author' field deprecated in favor of created_by_email

    class Config:
        from_attributes = True


class PromptsListResponse(BaseModel):
    totalCount: int
    items: list[PromptOut] = Field(default_factory=list)


class PromptUpdate(BaseModel):
    section: Optional[str] = None
    label: Optional[str] = None
    body: Optional[str] = None
    prompt_list: Optional[list[str]] = None
    market: Optional[str] = None
    property_type: Optional[str] = None
    tier: Optional[str] = None
    status: Optional[str] = None
    is_default: Optional[bool] = None
    # Note: 'author' field removed - use created_by tracking instead


class ReportSectionElementIn(BaseModel):
    element_type: str
    label: Optional[str] = None
    selected: bool = True
    display_order: int = 0
    config: Optional[dict] = None
    prompt_text: Optional[str] = None
    feedback_prompt: Optional[list["FeedbackPromptEntry"]] = None


class ReportSectionIn(BaseModel):
    key: str
    name: str
    sectionname_alias: Optional[str] = None
    display_order: int = 0
    selected: bool = True
    layout_preference: Optional[str] = None
    report_section_id: Optional[int] = None
    # Section-level slide placement within the PPT; optional and stored under element configs if DB lacks a column
    slide_number: Optional[int] = None
    prompt_template_id: Optional[int] = None
    prompt_template_label: Optional[str] = None
    prompt_template_body: Optional[str] = None
    elements: list[ReportSectionElementIn] = Field(default_factory=list)


class ReportCreate(BaseModel):
    name: str
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    report_type: Optional[str] = None
    prompt_template_id: Optional[int] = None
    prompt_template_label: Optional[str] = None
    division: list[str] | str = Field(default_factory=list)
    publishing_group: str
    property_type: str
    property_sub_type: Optional[str] = None
    status: Optional[str] = None
    automation_mode: str
    quarter: Optional[str] = None
    run_quarter: Optional[str] = None
    history_range: Optional[str] = None
    absorption_calculation: Optional[str] = None
    total_vs_direct_absorption: Optional[str] = None
    asking_rate_frequency: Optional[str] = None
    asking_rate_type: Optional[str] = None
    minimum_transaction_size: Optional[int] = None
    use_auto_generated_text: bool = True
    defined_markets: list[str] = Field(default_factory=list)
    vacancy_index: list[str] = Field(default_factory=list)
    submarket: list[str] = Field(default_factory=list)
    district: list[str] = Field(default_factory=list)
    sections: list[ReportSectionIn] = Field(default_factory=list)
    ppt_data: Optional[list] = None


class ReportSaveIn(BaseModel):
    """Minimal payload for saving edited report content in Step 2.

    Allows updating the report status and fully replacing the current sections
    with the provided list (including commentary text, feedback prompts, and
    element configs), without requiring the rest of the report metadata.
    """
    status: Optional[str] = None
    sections: Optional[list[ReportSectionIn]] = None


class ReportPatchIn(BaseModel):
    """Partial update payload for reports.

    Any provided top-level fields are patched. If `sections` is provided, the
    report's sections are replaced with the given list (mirrors PUT behavior).
    """
    # top-level fields (all optional)
    name: Optional[str] = None
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    report_type: Optional[str] = None
    prompt_template_id: Optional[int] = None
    prompt_template_label: Optional[str] = None
    division: Optional[list[str] | str] = None
    publishing_group: Optional[str] = None
    property_type: Optional[str] = None
    property_sub_type: Optional[str] = None
    status: Optional[str] = None
    automation_mode: Optional[str] = None
    quarter: Optional[str] = None
    run_quarter: Optional[str] = None
    history_range: Optional[str] = None
    absorption_calculation: Optional[str] = None
    total_vs_direct_absorption: Optional[str] = None
    asking_rate_frequency: Optional[str] = None
    asking_rate_type: Optional[str] = None
    minimum_transaction_size: Optional[int] = None
    use_auto_generated_text: Optional[bool] = None
    defined_markets: Optional[list[str]] = None
    vacancy_index: Optional[list[str]] = None
    submarket: Optional[list[str]] = None
    district: Optional[list[str]] = None
    # optional sections replacement
    sections: Optional[list[ReportSectionIn]] = None
    ppt_data: Optional[list] = None

class ReportSectionElementOut(ReportSectionElementIn):
    id: int

    class Config:
        from_attributes = True


class ReportSectionOut(ReportSectionIn):
    id: int
    elements: list[ReportSectionElementOut]

    class Config:
        from_attributes = True


class ReportEvaluationOut(BaseModel):
    id: int
    run_id: Optional[int] = None
    section_name: Optional[str] = None
    property_type: Optional[str] = None
    property_sub_type: Optional[str] = None
    division: Optional[str] = None
    publishing_group: Optional[str] = None
    automation_mode: Optional[str] = None
    quarter: Optional[str] = None
    history_range: Optional[str] = None
    absorption_calculation: Optional[str] = None
    total_vs_direct_absorption: Optional[str] = None
    asking_rate_frequency: Optional[str] = None
    asking_rate_type: Optional[str] = None
    defined_markets: Optional[list[str]] = None
    generated_commentary: Optional[str] = None
    ground_truth_commentary: Optional[str] = None
    evaluation_result: Dict[str, Any] = Field(default_factory=dict)
    model_details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackPromptEntry(BaseModel):
    feedback: Optional[str] = None
    commentary: Optional[str] = None
    timestamp: Optional[str] = None

    @classmethod
    def __get_validators__(cls):
        yield cls._convert

    @classmethod
    def _convert(cls, value):
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(**value)
        if isinstance(value, str):
            return cls(feedback=value)
        raise TypeError("Invalid feedback prompt entry format")


class PptUrlInfo(BaseModel):
    """Schema for individual PPT download information."""
    name: str = Field(description="Display name for the PPT (e.g., 'report_name-market_name')")
    ppt_url: str = Field(description="Download URL for this specific PPT")

    class Config:
        from_attributes = True


class ReportOut(BaseModel):
    id: int
    name: str
    status: str
    schedule_status: str
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    report_type: Optional[str] = None
    prompt_template_id: Optional[int] = None
    prompt_template_label: Optional[str] = None
    division: list[str] = Field(default_factory=list)
    publishing_group: str
    property_type: str
    property_sub_type: Optional[str] = None
    automation_mode: str
    quarter: Optional[str] = None
    run_quarter: Optional[str] = None
    history_range: Optional[str] = None
    absorption_calculation: Optional[str] = None
    total_vs_direct_absorption: Optional[str] = None
    asking_rate_frequency: Optional[str] = None
    asking_rate_type: Optional[str] = None
    minimum_transaction_size: Optional[int] = None
    use_auto_generated_text: bool
    defined_markets: Optional[list[str]] = None
    vacancy_index: Optional[list[str]] = None
    submarket: Optional[list[str]] = None
    district: Optional[list[str]] = None
    hero_fields: Optional[dict[str, Any]] = None
    ppt_url: Optional[list[PptUrlInfo]] = None
    s3_path: Optional[list[str]] = None
    market_ppt_mapping: Optional[dict[str, str]] = None
    created_at: datetime
    updated_at: datetime
    created_by_email: Optional[str] = None
    modified_by_email: Optional[str] = None
    sections: list[ReportSectionOut] = Field(default_factory=list)
    evaluations: list[ReportEvaluationOut] = Field(default_factory=list)

    class Config:
        from_attributes = True

    @field_validator("ppt_url", mode="before")
    @classmethod
    def _normalize_report_ppt_urls(cls, value):
        return _normalize_ppt_url_entries(value)


class ReportConfigIn(BaseModel):
    name: str
    report_type: str
    market: str
    property_type: str
    defined_markets: list[str] = Field(default_factory=list)
    automation_mode: Optional[str] = None
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    revenue_period: Optional[str] = None
    sections: Optional[dict] = None


class ScheduleIn(BaseModel):
    name: str
    report_id: Optional[int] = None
    report_ids: Optional[list[int]] = None
    report_name: Optional[str] = None
    recurrence: str
    recipients: list[str]
    next_run_at: Optional[datetime] = None
    time_of_day: Optional[str] = None  # 'HH:MM'
    day_of_week: Optional[str] = None  # Monday..Sunday
    day_of_month: Optional[int] = None  # 1-31 for monthly/quarterly/yearly
    month_of_year: Optional[int] = None  # 1-12 for yearly
    month_of_quarter: Optional[int] = None  # 1-3 for quarterly (1=first month, 2=second, 3=third)
    start_date: Optional[datetime] = None
    run_date: Optional[datetime] = None


class ScheduleOut(BaseModel):
    id: int
    name: str
    recurrence: str
    schedule_status: str
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    report_id: Optional[int] = None
    report_name: Optional[str] = None
    recipients: list[str] = Field(default_factory=list)
    created_at: datetime
    created_by_email: Optional[str] = None
    modified_by_email: Optional[str] = None
    time_of_day: Optional[str] = None
    day_of_week: Optional[str] = None
    day_of_month: Optional[int] = None
    month_of_year: Optional[int] = None
    month_of_quarter: Optional[int] = None
    start_date: Optional[datetime] = None
    run_date: Optional[datetime] = None

    class Config:
        from_attributes = True


class SchedulesListResponse(BaseModel):
    totalCount: int
    items: list[ScheduleOut] = Field(default_factory=list)


class ReportRunOut(BaseModel):
    id: int
    report_id: Optional[int] = None
    report_name: Optional[str] = None
    report_type: Optional[str] = None
    market: Optional[str] = None
    property_type: Optional[str] = None
    property_sub_type: Optional[str] = None
    created_at: datetime
    status: str
    run_state: Optional[str] = None
    trigger_source: str = "manual"
    output_formats: Optional[str] = None
    duration_seconds: Optional[int] = None
    s3_path: Optional[str] = None
    created_by_email: Optional[str] = None
    schedule_id: Optional[int] = None


class ReportListOut(BaseModel):
    id: int
    name: str
    template_name: Optional[str] = None
    sections: list[str] = Field(default_factory=list)
    status: Optional[str] = None
    schedule_status: Optional[str] = None
    automation_mode: Optional[str] = None
    property_type: Optional[str] = None
    property_sub_type: Optional[str] = None
    market: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    ppt_url: Optional[list[PptUrlInfo]] = None
    created_by_email: Optional[str] = None
    modified_by_email: Optional[str] = None

    class Config:
        from_attributes = True

    @field_validator("ppt_url", mode="before")
    @classmethod
    def _normalize_list_ppt_urls(cls, value):
        return _normalize_ppt_url_entries(value)


class ReportListResponse(BaseModel):
    totalCount: int
    items: list[ReportListOut] = Field(default_factory=list)


class ReportHistoryListResponse(BaseModel):
    totalCount: int
    items: list[ReportRunOut] = Field(default_factory=list)


class ReportRunsListResponse(BaseModel):
    totalCount: int
    items: list[dict] = Field(default_factory=list)


class ReportSummaryOut(BaseModel):
    id: int
    name: str
    report_type: Optional[str] = None
    market: Optional[str] = None
    property_type: Optional[str] = None
    property_sub_type: Optional[str] = None
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    last_duration_seconds: Optional[int] = None
    last_trigger_source: Optional[str] = None
    last_triggered_by_email: Optional[str] = None
    scheduled: bool = False
    next_run_at: Optional[datetime] = None
    schedule_status: Optional[str] = None
    recipients: list[str] = Field(default_factory=list)
    created_by_email: Optional[str] = None


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    report_id: Optional[int] = None
    # Accept either 'recurrence' or legacy 'frequency'
    recurrence: Optional[str] = None
    frequency: Optional[str] = None
    # Allow array or CSV string; router normalizes
    recipients: Optional[list[str] | str] = None
    status: Optional[str] = None
    next_run_at: Optional[datetime] = None
    time_of_day: Optional[str] = None
    day_of_week: Optional[str] = None
    day_of_month: Optional[int] = None
    month_of_year: Optional[int] = None
    month_of_quarter: Optional[int] = None
    start_date: Optional[datetime] = None
    run_date: Optional[datetime] = None


# Multi-Agent Workflow Models
class WorkflowRequest(BaseModel):
    session_type: str = Field(
        ...,
        description="Type of session for analysis (e.g., 'vacancy', 'leasing')",
        example="vacancy",
    )
    input_data: str = Field(
        ...,
        description="JSON string containing the data to analyze",
        example="[{'Quarter': 'Q2 2025', 'Overall': 18.29, 'Class A': 20.4, 'Class B': 18.4}]",
    )
    timeout: Optional[float] = Field(
        default=300.0,
        description="Execution timeout in seconds (default: 300s)",
        ge=30.0,
        le=600.0,
    )


class WorkflowResponse(BaseModel):
    success: bool = Field(description="Whether the workflow executed successfully")
    summary_result: Optional[str] = Field(
        default=None, description="Generated summary text from the workflow"
    )
    workflow_approved: bool = Field(
        default=False,
        description="Whether the workflow was approved by validation agents",
    )
    retry_counts: Dict[str, int] = Field(
        default_factory=dict, description="Number of retries for each agent type"
    )
    improvement_feedback: Optional[str] = Field(
        default=None, description="Feedback collected from failed validations"
    )
    validation_results: Dict[str, Any] = Field(
        default_factory=dict, description="Results from validation agents"
    )
    execution_time: float = Field(
        description="Time taken to execute the workflow in seconds"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if workflow failed"
    )


class WorkflowStatusResponse(BaseModel):
    ready: bool = Field(description="Whether the single workflow service is ready")
    parallel_ready: bool = Field(
        description="Whether the parallel workflow service is ready"
    )
    initialized: bool = Field(description="Whether the service has been initialized")
    error: Optional[str] = Field(
        default=None, description="Initialization error if any"
    )
    workflow_compiled: bool = Field(
        description="Whether the single workflow graph is compiled"
    )
    parallel_workflow_compiled: bool = Field(
        description="Whether the parallel workflow graph is compiled"
    )


# Parallel Multi-Section Workflow Models
class SectionRequest(BaseModel):
    section_id: str = Field(
        description="Unique identifier for the section", example="vacancy_analysis"
    )
    section_name: str = Field(
        description="Human-readable name for the section",
        example="Vacancy Rate Analysis",
    )
    session_type: str = Field(
        description="Type of session for this section (e.g., 'vacancy', 'leasing')",
        example="vacancy",
    )
    input_data: List[str] = Field(
        description="Multiple JSON string containing the data to analyze for this section",
        examples=["[{'Quarter': 'Q2 2025', 'Overall': 18.29, 'Class A': 20.4}]", "[{'Quarter': 'Q2 2025', 'Overall': 18.29, 'Class A': 20.4}]"]
    )
    prompt: dict = Field(
        default=None,
        description="Prompt configuration for generating commentary for this section",
        example={"consolidation_prompt": "Analyze the following vacancy data and provide insights.",
                 "sql_prompts": ["prompt1", "prompt2"]},
    )
    feedback: Optional[str] = Field(
        default=None, description="Optional user feedback for the previously generated commentary."
    )


class SectionResponse(BaseModel):
    section_id: str = Field(description="Unique identifier for the section")
    section_name: str = Field(description="Human-readable name for the section")
    success: bool = Field(description="Whether the section processing succeeded")
    summary_result: Optional[str] = Field(
        default=None, description="Generated summary text for this section"
    )
    summary_results: List[str] = Field(
        default=None, description="Summary results for this section"
    )
    workflow_approved: bool = Field(
        default=False, description="Whether this section's workflow was approved"
    )
    retry_counts: Dict[str, int] = Field(
        default_factory=dict, description="Number of retries for each agent type"
    )
    improvement_feedback: Optional[str] = Field(
        default=None, description="Feedback collected from failed validations"
    )
    validation_results: Dict[str, Any] = Field(
        default_factory=dict, description="Results from validation agents"
    )
    execution_time: float = Field(
        description="Time taken to process this section in seconds"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if section processing failed"
    )


class ParallelExecutionStats(BaseModel):
    total_sections: int = Field(description="Total number of sections processed")
    successful_sections: int = Field(description="Number of sections that succeeded")
    failed_sections: int = Field(description="Number of sections that failed")
    total_execution_time: float = Field(description="Total parallel execution time")
    average_section_time: float = Field(description="Average time per section")
    max_section_time: float = Field(description="Longest section processing time")
    min_section_time: float = Field(description="Shortest section processing time")


class ParallelWorkflowRequest(BaseModel):
    sections: List[SectionRequest] = Field(
        description="List of sections to process in parallel",
        min_length=1,
        max_length=10,  # Reasonable limit for parallel processing
        example=[
            {
                "section_id": "vacancy_analysis",
                "section_name": "Vacancy Rate Analysis",
                "session_type": "vacancy",
                "input_data": "[{'Quarter': 'Q2 2025', 'Overall': 18.29}]",
            },
            {
                "section_id": "leasing_activity",
                "section_name": "Leasing Activity Summary",
                "session_type": "leasing",
                "input_data": "[{'Quarter': 'Q2 2025', 'Net_Absorption': 250000}]",
            },
        ],
    )
    timeout: Optional[float] = Field(
        default=1500.0,
        description="Execution timeout in seconds per section (default: 1500s)",
        ge=30.0,
        le=1500.0,
    )


class ParallelWorkflowResponse(BaseModel):
    success: bool = Field(
        description="Whether the parallel workflow executed successfully"
    )
    section_results: Dict[str, SectionResponse] = Field(
        description="Results for each section, keyed by section_id"
    )
    parallel_stats: ParallelExecutionStats = Field(
        description="Statistics about the parallel execution"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if parallel workflow failed"
    )


class GenerateTitleRequest(BaseModel):
    sections_commentary: list[str]

class GenerateTitleResponse(BaseModel):
    title_sequence: dict[str, str]

from __future__ import annotations, division

from datetime import datetime
from typing import Optional, Any
import json

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    Text,
    ForeignKey,
    DateTime,
    JSON,
    CheckConstraint,
    UniqueConstraint,
    Table,
    Column,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator
from sqlalchemy.ext.mutable import MutableList

from hello.services.database import Base
from sqlalchemy.dialects.postgresql import TEXT as PG_TEXT, ARRAY
from sqlalchemy.types import TypeDecorator


class _ArrayOfText(TypeDecorator):
    """Store lists as Postgres ARRAYs or JSON strings on SQLite."""

    impl = ARRAY(PG_TEXT)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return Text()
        return ARRAY(PG_TEXT)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "sqlite":
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return [] if dialect.name == "sqlite" else value
        if dialect.name == "sqlite":
            try:
                return json.loads(value)
            except Exception:
                return []
        return value


PromptListType = MutableList.as_mutable(_ArrayOfText())


template_section_association = Table(
    "template_section_templates",
    Base.metadata,
    Column("template_id", ForeignKey("templates.id", ondelete="CASCADE"), primary_key=True),
    Column("section_id", ForeignKey("template_sections.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime, default=datetime.utcnow, nullable=False),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(128))
    miq_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    base_type: Mapped[str] = mapped_column(
        String(64)
    )  # Office Figures / Industrial Figures
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    attended: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    last_modified: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )
    ppt_status: Mapped[str] = mapped_column(String(32), default="Not Attached")
    ppt_s3_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ppt_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    ppt_attached_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    modified_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    sections: Mapped[list["TemplateSection"]] = relationship(
        "TemplateSection",
        secondary=template_section_association,
        back_populates="templates",
        order_by="TemplateSection.created_at",
    )
    created_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by]
    )
    modified_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[modified_by]
    )
    reports: Mapped[list["Report"]] = relationship(
        "Report",
        back_populates="template",
        passive_deletes=True,
        cascade="save-update, merge",
    )


class TemplateSection(Base):
    __tablename__ = "template_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))  # e.g., Executive Summary
    sectionname_alias: Mapped[str] = mapped_column(String(255))
    label: Mapped[Optional[str]] = mapped_column(String(255))
    property_type: Mapped[str] = mapped_column(String(64))  # Office/Industrial
    property_sub_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tier: Mapped[Optional[str]] = mapped_column(String(32))
    markets: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    division: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    publishing_group: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    automation_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    quarter: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    history_range: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    absorption_calculation: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    total_vs_direct_absorption: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    asking_rate_frequency: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    asking_rate_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    minimum_transaction_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    use_auto_generated_text: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    report_parameters: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    vacancy_index: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    submarket: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    district: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    default_prompt: Mapped[Optional[Text]] = mapped_column(Text)
    # New: Persist finalized commentary preview and prompt fields at section level
    commentary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    adjust_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chart_config: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    table_config: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    slide_layout: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )  # Attended/Unattended
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    modified_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    templates: Mapped[list["Template"]] = relationship(
        "Template",
        secondary=template_section_association,
        back_populates="sections",
    )
    created_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by]
    )
    modified_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[modified_by]
    )
    elements: Mapped[list["TemplateSectionElement"]] = relationship(
        "TemplateSectionElement",
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="TemplateSectionElement.display_order",
    )
    @property
    def template_ids(self) -> list[int]:
        return [tpl.id for tpl in self.templates]


class TemplateSectionElement(Base):
    __tablename__ = "template_section_elements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("template_sections.id", ondelete="CASCADE"), index=True
    )
    element_type: Mapped[str] = mapped_column(String(32))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    section: Mapped[TemplateSection] = relationship(back_populates="elements")





class PromptListType(TypeDecorator):
    """Use ARRAY on Postgres and JSON on SQLite (for tests)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(JSON())
        return dialect.type_descriptor(ARRAY(PG_TEXT))


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section: Mapped[str] = mapped_column(String(255))
    label: Mapped[str] = mapped_column(String(255))
    market: Mapped[Optional[str]] = mapped_column(String(128))
    property_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tier: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="Active")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # Versioning for prompt revisions; starts at 1 for new prompts
    version: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[str] = mapped_column(PG_TEXT)
    prompt_list: Mapped[list[str]] = mapped_column(
        PromptListType(), default=list, nullable=False
    )
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    downvotes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_modified: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    modified_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by]
    )
    modified_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[modified_by]
    )


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("name", name="uq_reports_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL"), nullable=True
    )
    template_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    report_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt_template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True
    )
    prompt_template_label: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="Draft")
    schedule_status: Mapped[str] = mapped_column(String(32), default="NA")
    division: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    publishing_group: Mapped[str] = mapped_column(String(128))
    property_type: Mapped[str] = mapped_column(String(64))
    property_sub_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    automation_mode: Mapped[str] = mapped_column(String(32))
    quarter: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    run_quarter: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    history_range: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    absorption_calculation: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    total_vs_direct_absorption: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    asking_rate_frequency: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    asking_rate_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    minimum_transaction_size: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    use_auto_generated_text: Mapped[bool] = mapped_column(Boolean, default=True)
    defined_markets: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    vacancy_index: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    submarket: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    district: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    hero_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    ppt_url: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=list)  # List of {name, ppt_url}
    s3_path: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    market_ppt_mapping: Mapped[dict[str, str] | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    modified_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    template: Mapped[Optional[Template]] = relationship(
        "Template", lazy="joined", passive_deletes=True, back_populates="reports"
    )
    prompt_template: Mapped[Optional[Prompt]] = relationship("Prompt", lazy="joined")
    created_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by]
    )
    modified_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[modified_by]
    )
    sections: Mapped[list["ReportSection"]] = relationship(
        "ReportSection",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportSection.display_order",
        lazy="joined",
    )


class ReportSection(Base):
    __tablename__ = "report_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    sectionname_alias: Mapped[str] = mapped_column(String(255))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    prompt_template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True
    )
    prompt_template_label: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    prompt_template_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    layout_preference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    report: Mapped[Report] = relationship(back_populates="sections")
    prompt_template: Mapped[Optional[Prompt]] = relationship("Prompt", lazy="joined")
    elements: Mapped[list["ReportSectionElement"]] = relationship(
        "ReportSectionElement",
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="ReportSectionElement.display_order",
        lazy="joined",
    )


class ReportSectionElement(Base):
    __tablename__ = "report_section_elements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_section_id: Mapped[int] = mapped_column(
        ForeignKey("report_sections.id", ondelete="CASCADE"), index=True
    )
    element_type: Mapped[str] = mapped_column(String(32))
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    # New: store the final commentary text captured for this section element
    section_commentary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_prompt: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    section: Mapped[ReportSection] = relationship(back_populates="elements")


class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="Draft")
    s3_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_formats: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    trigger_source: Mapped[str] = mapped_column(String(32), default="manual")
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    created_by_user: Mapped[Optional["User"]] = relationship("User")
    report: Mapped[Optional["Report"]] = relationship("Report")


class ReportRun(Base):
    __tablename__ = "report_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )
    schedule_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True
    )
    trigger_source: Mapped[str] = mapped_column(String(32), default="manual")
    run_time_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    report_name: Mapped[str] = mapped_column(String(255))
    report_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    market: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    sections: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    status: Mapped[str] = mapped_column(String(32), default="Success")
    run_state: Mapped[str] = mapped_column(String(128), default="completed")
    output_format: Mapped[str] = mapped_column(String(32), default="ppt")
    ppt_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    s3_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    email_delivery_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by]
    )
    schedule: Mapped[Optional["Schedule"]] = relationship("Schedule")


class Schedule(Base):
    __tablename__ = "schedules"
    __table_args__ = (UniqueConstraint("name", name="uq_schedules_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    report_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )
    frequency: Mapped[str] = mapped_column(String(32))  # Daily/Weekly/...
    recipients: Mapped[Optional[str]] = mapped_column(Text)  # csv list
    status: Mapped[str] = mapped_column(String(32), default="Active")  # legacy
    schedule_status: Mapped[str] = mapped_column(String(32), default="active")
    time_of_day: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    day_of_week: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    day_of_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    month_of_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-12 for yearly
    month_of_quarter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-3 for quarterly
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    run_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    modified_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


# ==========================
# Agent conversations + messages
# ==========================


class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Scope conversations to a specific report when generating within Step 2
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=True
    )
    # Also scope to the concrete report section instance
    report_section_id: Mapped[int | None] = mapped_column(
        ForeignKey("report_sections.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_name: Mapped[str] = mapped_column(Text)  # e.g., 'agent-summary', 'agent-rent'
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    meta: Mapped[dict] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    messages: Mapped[list["AgentMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(
        String(16),
        CheckConstraint(
            "role in ('user','agent','system','tool')", name="agent_messages_role_check"
        ),
    )
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default={})
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped[AgentConversation] = relationship(back_populates="messages")


class GroundTruthCommentary(Base):
    __tablename__ = "ground_truth_commentaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_name: Mapped[str] = mapped_column(String(255), nullable=True)
    property_type: Mapped[str] = mapped_column(String(64), nullable=True)
    property_sub_type: Mapped[str] = mapped_column(String(64), nullable=True)
    quarter: Mapped[str] = mapped_column(String(32), nullable=True)
    automation_mode: Mapped[str] = mapped_column(String(32), nullable=True)
    division: Mapped[str] = mapped_column(String(128), nullable=True)
    publishing_group: Mapped[str] = mapped_column(String(128), nullable=True)
    defined_markets: Mapped[list[str]] = mapped_column(JSON, default=list)
    history_range: Mapped[str] = mapped_column(String(64), nullable=True)
    absorption_calculation: Mapped[str] = mapped_column(String(64), nullable=True)
    total_vs_direct_absorption: Mapped[str] = mapped_column(String(32), nullable=True)
    asking_rate_frequency: Mapped[str] = mapped_column(String(32), nullable=True)
    asking_rate_type: Mapped[str] = mapped_column(String(32), nullable=True)
    ground_truth_commentary: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class CommentaryEvaluation(Base):
    __tablename__ = "commentary_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("report_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    section_name: Mapped[str] = mapped_column(String(255), nullable=True)
    property_type: Mapped[str] = mapped_column(String(64), nullable=True)
    property_sub_type: Mapped[str] = mapped_column(String(64), nullable=True)
    quarter: Mapped[str] = mapped_column(String(32), nullable=True)
    automation_mode: Mapped[str] = mapped_column(String(32), nullable=True)
    division: Mapped[str] = mapped_column(String(128), nullable=True)
    publishing_group: Mapped[str] = mapped_column(String(128), nullable=True)
    defined_markets: Mapped[list[str]] = mapped_column(JSON, default=list)
    history_range: Mapped[str] = mapped_column(String(64), nullable=True)
    absorption_calculation: Mapped[str] = mapped_column(String(64), nullable=True)
    total_vs_direct_absorption: Mapped[str] = mapped_column(String(32), nullable=True)
    asking_rate_frequency: Mapped[str] = mapped_column(String(32), nullable=True)
    asking_rate_type: Mapped[str] = mapped_column(String(32), nullable=True)
    ground_truth_commentary: Mapped[str] = mapped_column(Text, nullable=True)
    generated_commentary: Mapped[str] = mapped_column(Text, nullable=True)
    evaluation_result: Mapped[dict] = mapped_column(JSON, default=dict)
    model_details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

"""데이터베이스 스키마.

설계 원칙:
  - 사용자가 쓴 소스는 리비전으로 남긴다. 시뮬레이션 결과는 "그때 그 소스"와
    짝지어져야 재현이 가능하다. 소스를 덮어쓰면 과거 잡의 입력을 잃는다.
  - 잡은 소스 리비전을 참조한다. 프로젝트를 참조하면 나중에 소스가 바뀌었을 때
    결과와 입력이 어긋난다.
  - 산출물(.str)은 파일시스템에 두고 DB 에는 경로와 메타데이터만 둔다.
    CMOS 예제 한 번에 5MB 가 나오므로 DB 에 넣을 크기가 아니다.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(enum.Enum):
    """잡 생애주기.

    SUCCEEDED 판정은 종료 코드가 아니라 로그 분석에 근거한다. 시뮬레이터는
    커맨드 오류가 있어도 exit 0 으로 끝나기 때문이다(runner/results.py 참조).
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self not in (JobStatus.QUEUED, JobStatus.RUNNING)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    #: argon2id 해시. 평문은 어떤 형태로도 저장하지 않는다.
    password_hash: Mapped[str] = mapped_column(String(255))
    #: 'user' 또는 'admin'. admin 은 동시 접속 정원과 유휴 만료를 면제받는다.
    role: Mapped[str] = mapped_column(String(16), default="user")
    is_active: Mapped[bool] = mapped_column(default=True)
    #: 어떤 초대로 가입했는지. 나중에 계정 출처를 따질 수 있어야 한다.
    #: CLI 로 만든 첫 관리자는 초대가 없으므로 NULL.
    #: 제약에 이름을 준다. 이름이 없으면 downgrade 에서 DROP CONSTRAINT 를
    #: 만들 수 없어 롤백이 막힌다.
    invite_code_id: Mapped[int | None] = mapped_column(
        # users 와 invite_codes 가 서로를 참조한다(초대는 발급자를, 사용자는
        # 자기 초대를 가리킨다). use_alter 로 이 제약을 테이블 생성 뒤에 걸어야
        # 생성 순서를 정할 수 있다.
        ForeignKey(
            "invite_codes.id",
            ondelete="SET NULL",
            name="fk_users_invite_code_id",
            use_alter=True,
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    projects: Mapped[list[Project]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("role in ('user','admin')", name="ck_users_role"),
    )


class Project(Base):
    """작업 단위. 소스 리비전과 잡을 묶는다."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[User] = relationship(back_populates="projects")
    revisions: Mapped[list[SourceRevision]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_projects_owner_name"),
    )


class SourceRevision(Base):
    """`.in` 소스의 한 판본.

    잡이 이걸 참조하므로 한 번 만들어진 리비전은 수정하지 않는다. 수정하면
    이미 끝난 잡의 입력이 뒤바뀌어 결과를 재현할 수 없게 된다.
    """

    __tablename__ = "source_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    #: 프로젝트 안에서 1부터 증가하는 번호. 사용자에게 보여주는 값이다.
    revision: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="revisions")
    jobs: Mapped[list[Job]] = relationship(back_populates="source_revision")

    __table_args__ = (
        UniqueConstraint(
            "project_id", "revision", name="uq_source_revisions_project_revision"
        ),
    )


class Job(Base):
    """시뮬레이션 실행 한 건."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_revision_id: Mapped[int] = mapped_column(
        ForeignKey("source_revisions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", native_enum=False),
        default=JobStatus.QUEUED,
    )
    #: 잡 전용 스크래치 디렉토리. 컨테이너가 쓸 수 있는 유일한 호스트 경로다.
    workdir: Mapped[str] = mapped_column(String(512))
    #: stdout 과 stderr 를 합친 로그. 시뮬레이터 오류가 stderr 로 나가므로
    #: 분리해 저장하면 실패 원인이 사라진다.
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    source_revision: Mapped[SourceRevision] = relationship(back_populates="jobs")
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # 큐가 대기 중인 잡을 오래된 순으로 꺼낸다.
        Index("ix_jobs_status_created", "status", "created_at"),
    )


class Artifact(Base):
    """잡이 만들어낸 `.str` 파일 하나.

    내용은 파일시스템에 있고 여기에는 경로와 메타데이터만 둔다. CMOS 예제는
    한 번 실행에 15개 약 5MB 가 나온다.
    """

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    #: `structure out=` 에 적힌 이름. 공정 단계를 알아보는 단서가 된다.
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    #: 생성 순서. 이름순이 아니라 이 순서여야 공정 흐름과 일치한다.
    sequence: Mapped[int] = mapped_column(Integer)

    job: Mapped[Job] = relationship(back_populates="artifacts")

    __table_args__ = (
        UniqueConstraint("job_id", "sequence", name="uq_artifacts_job_sequence"),
    )


class InviteCode(Base):
    """가입 초대 코드.

    가입을 열어 두면 도메인을 찾은 누구나 홈서버 컨테이너 안에서 코드를 실행할
    수 있다. 격리는 별개로 튼튼하지만, 모르는 사람이 서버 자원을 쓰는 것 자체를
    막아야 한다.

    코드는 **argon2 가 아니라 SHA-256** 으로 저장한다. argon2 는 솔트가 섞여
    있어 해시로 행을 찾을 수 없고, 가입 시도마다 모든 초대를 하나씩 검증해야
    한다 — 느릴 뿐 아니라 그 자체가 DoS 벡터다. 초대 코드는 비밀번호와 달리
    256비트 무작위라 느린 해시로 무차별 대입을 늦출 이유가 없다.
    """

    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: SHA-256 hex. 평문은 발급 순간에만 존재하고 저장하지 않는다.
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    #: 발급자. 계정이 지워져도 발급 이력은 남겨야 하므로 NULL 허용.
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    #: 회수 시각. 재배포 없이 즉시 막기 위한 것이라 행을 지우지 않는다.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint("max_uses > 0", name="ck_invite_codes_max_uses"),
        CheckConstraint("used_count >= 0", name="ck_invite_codes_used_count"),
    )

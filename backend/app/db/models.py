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
    # cascade 를 적지 않으면 ORM 이 스키마와 반대로 움직인다. 컬럼에는
    # ON DELETE CASCADE 가 걸려 있는데, 관계에 아무 것도 없으면 SQLAlchemy 는
    # 리비전을 지울 때 잡의 FK 를 NULL 로 만들려 하고 NOT NULL 에 걸려 터진다
    # (프로젝트 삭제를 붙이면서 실제로 그렇게 터졌다).
    jobs: Mapped[list[Job]] = relationship(
        back_populates="source_revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "revision", name="uq_source_revisions_project_revision"
        ),
    )


class JobKind:
    """잡의 종류.

    Enum 이 아니라 문자열 상수인 이유: 값이 DB 에 그대로 들어가고, 종류가 늘 때
    마이그레이션 없이 읽을 수 있어야 한다. `status` 는 상태 기계라 Enum 이지만
    이쪽은 그냥 꼬리표다.
    """

    SUPREM = "suprem"
    DEVSIM = "devsim"

    ALL = (SUPREM, DEVSIM)


class Job(Base):
    """시뮬레이션 실행 한 건.

    두 종류가 같은 표를 쓴다. 큐·중단·타임아웃·로그·산출물·청소가 전부 같고,
    다른 것은 워커가 무엇을 부르느냐뿐이다. 표를 나누면 그 공통 부분을 전부
    두 벌로 만들어야 한다.
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: 무엇을 돌리는 잡인가. `suprem` 은 `source` 가 공정 코드이고, `devsim` 은
    #: `source` 가 해석 조건(JSON)이며 구조는 workdir 에 놓인다.
    kind: Mapped[str] = mapped_column(String(16), default=JobKind.SUPREM)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    #: 예전 프로젝트 모델의 잔재. 파일 기반 실행에서는 비어 있다.
    source_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    #: 작업공간 기준 경로. 어느 파일을 돌렸는지 알아보는 단서다.
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    #: 제출 시점의 소스 스냅샷. **파일이 그 뒤 바뀌어도 결과는 재현 가능해야
    #: 한다** — 경로만 들고 있으면 나중에 읽은 내용이 그때 돌린 것과 다르다.
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        CheckConstraint("kind in ('suprem', 'devsim')", name="ck_jobs_kind"),
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


class SavedStructure(Base):
    """소자 해석에 쓸 수 있는 `.str` 을 오래 보관한다.

    **왜 잡 산출물을 그대로 쓰지 않는가.** 산출물은 유휴 스윕과 쿼터 스윕에
    지워진다(`app/jobs/sweeper.py`). 공정을 돌린 다음 날 소자 해석을 하려면
    그때마다 공정을 다시 돌려야 한다는 뜻이다.

    **왜 전부 보관하지 않는가.** 25단계 흐름이면 산출물이 25개 17MB 인데, 그중
    전극이 있는 것은 보통 마지막 한두 개뿐이다(`app/devsim/screening.py`).

    같은 `.in` 을 다시 돌리면 그 `.in` 에서 나온 것은 전부 지우고 새로 채운다.
    공정 코드를 고쳐 다시 돌렸는데 옛 구조가 목록에 남아 있으면, 어느 것이
    지금 코드의 결과인지 구분할 수 없다.
    """

    __tablename__ = "saved_structures"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    #: 이 구조를 만든 `.in` 의 작업공간 기준 경로. 다시 돌릴 때의 열쇠다.
    source_path: Mapped[str] = mapped_column(String(1024))
    #: 만들어 낸 잡. 잡이 지워져도 구조는 남아야 하므로 끊어질 수 있다.
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #: 공정 단계 순서. 결과 화면에서 넘어올 때 짝을 찾는 데 쓴다.
    sequence: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    #: 보관 위치. 잡 작업디렉토리 밖이라 스윕이 건드리지 않는다.
    path: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_id", "source_path", "filename", name="uq_saved_structures_name"
        ),
    )


class DevSimResult(Base):
    """사용자가 **이름을 붙여 저장한** 소자 해석 결과.

    돌린 것을 전부 남기지 않는다. 조건을 조금씩 바꿔 가며 여남은 번 돌리는 것이
    보통인데 그것이 다 목록에 쌓이면, 정작 비교하고 싶은 둘을 그 안에서 찾아야
    한다. 남길 것은 사용자가 고른다.

    **왜 workdir 이 아니라 DB 인가.** 산출물은 유휴 스윕과 쿼터 스윕에 지워진다
    (`app/jobs/sweeper.py`). 저장한 결과가 며칠 뒤 사라지면 저장한 의미가 없다.
    곡선 하나가 수백 행짜리 JSON 이라 표에 두어도 작다.

    스펙도 함께 남긴다. 비교 화면에서 "무엇이 달랐나"를 보여주려면 그때의 조건이
    있어야 한다.
    """

    __tablename__ = "devsim_results"

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    #: 사용자가 붙인 이름. 비교 화면의 범례에 나온다.
    label: Mapped[str] = mapped_column(String(120))
    #: 어느 구조에서 왔는지. 원본 잡이 지워져도 설명은 남는다.
    structure: Mapped[str] = mapped_column(String(255))
    #: 그 구조를 만든 `.in` 의 경로. 비교 화면에서 "어느 공정 코드에서 나온
    #: 결과인가" 를 보여주려면 이것이 있어야 한다 — 구조 파일 이름만으로는
    #: 여러 흐름에서 같은 이름이 나올 수 있다.
    source_path: Mapped[str] = mapped_column(String(1024), default="")
    #: 제출한 해석 조건(JSON).
    spec: Mapped[str] = mapped_column(Text)
    #: 곡선 데이터(JSON). `iv.json` 과 같은 모양이다.
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DevSimState(Base):
    """소자 해석 조건을 사용자별로 맡아 둔다.

    전극에 이름을 붙이고 계면을 붙이고 전압을 정하는 데는 손이 꽤 간다. 그런데
    새로고침 한 번에 그것이 전부 초기값으로 돌아갔다 — 편집기 탭을 맡아 두는
    것과 같은 이유로 여기도 맡아 둔다(`EditorState`).

    **열쇠가 구조 id 가 아니라 `.in` 경로다.** 같은 공정 코드를 다시 돌리면
    구조는 새로 생기고 옛것은 지워지는데(`app/devsim/catalog.py`), 구조 id 에
    매달아 두면 코드를 한 번 고칠 때마다 조건도 함께 사라진다. 사용자가 기억하는
    단위는 "내 nmos 설정" 이지 특정 실행이 아니다.

    조건이 지금 구조에 안 맞으면(계면 이름이 달라졌다든지) 읽는 쪽에서 버리고
    기본값으로 돌아간다. 맞지 않는 조건을 억지로 되살리면 사용자는 자기가 짠
    적 없는 설정을 자기 것으로 알고 읽게 된다.
    """

    __tablename__ = "devsim_states"

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    source_path: Mapped[str] = mapped_column(String(1024), primary_key=True)
    #: 해석 조건(JSON). 통째로 두는 이유는 EditorState 와 같다 — 칼럼으로 쪼개면
    #: 조건 모양이 바뀔 때마다 마이그레이션이 따라붙는다.
    spec: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
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


class EditorState(Base):
    """사용자가 편집기에 열어 둔 것.

    세션은 30분 유휴로 끊긴다. 다시 들어왔을 때 빈 화면이면 어느 파일을 보고
    있었는지, 어디까지 고쳤는지 사용자가 기억해서 되짚어야 한다. 그래서
    **열어 둔 탭·활성 탭·커서 위치·저장하지 않은 초안**을 사용자별로 남긴다.

    브라우저(localStorage)가 아니라 서버에 두는 이유는 두 가지다. 한 컴퓨터를
    여러 사람이 쓰면 저장소가 섞이고, 다른 컴퓨터로 옮기면 따라오지 않는다.

    내용은 JSON 문자열 하나다. 모양이 화면 사정으로 자주 바뀌는 값이라 컬럼으로
    쪼개면 마이그레이션이 계속 따라다닌다. 형태 검증은 API 경계에서 한다.
    """

    __tablename__ = "editor_states"

    #: 사용자당 하나. 별도 id 를 두면 같은 사용자의 행이 여럿 생길 수 있다.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

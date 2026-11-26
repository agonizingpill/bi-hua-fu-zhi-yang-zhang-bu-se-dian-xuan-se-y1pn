from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Table, text

from core.db import metadata


dry_swatches = Table('dry_swatches', metadata,
    Column('code', String(64), primary_key=True),
    Column('family', String(160), nullable=False),
    Column('fraction', Float, nullable=False),
    Column('ground_l', Float, nullable=False),
    Column('delta_e', Float, nullable=False),
    Column('sample_ref', String(160), nullable=False, unique=True),
    Column('dry_hours', Integer, nullable=False),
    Column('witnessed', Boolean, nullable=False),
    # 凭证撤回（抄错干样色差）后的登记状态。withdrawn/revoked 同义，state 用现场中文状态。
    Column('withdrawn', Boolean, nullable=False, server_default=text('false')),
    Column('revoked', Boolean, nullable=False, server_default=text('false')),
    Column('state', String(32), nullable=True),
    Column('withdraw_reason', String(240), nullable=True),
    Column('withdrawn_by', String(160), nullable=True),
    Column('withdrawn_at', DateTime(timezone=True), nullable=True),
    Column('superseded_by_code', String(64), nullable=True),
    Column('superseded_by_ref', String(160), nullable=True),
    CheckConstraint('fraction BETWEEN 0 AND 1'),
    CheckConstraint('ground_l BETWEEN 0 AND 100'),
    CheckConstraint('delta_e >= 0'),
    CheckConstraint('dry_hours BETWEEN 0 AND 240'),
)


# 点测凭证撤回登记簿：撤回先在此登记，签认事务加锁读取，形成顺序屏障。
ref_withdrawals = Table('ref_withdrawals', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('ref', String(160), nullable=False, index=True),
    Column('sample_ref', String(160), nullable=True),
    Column('voucher', String(160), nullable=True),
    Column('swatch_code', String(64), nullable=True, index=True),
    Column('bad_delta_e', Float, nullable=True),
    Column('reading', JSON, nullable=True),
    Column('reason', String(240), nullable=True),
    Column('actor', String(160), nullable=True),
    Column('status', String(32), nullable=False, server_default=text("'已撤回'")),
    Column('replaced_by_code', String(64), nullable=True),
    Column('replaced_by_ref', String(160), nullable=True),
    Column('created_at', DateTime(timezone=True), nullable=True),
    Column('resolved_at', DateTime(timezone=True), nullable=True),
)

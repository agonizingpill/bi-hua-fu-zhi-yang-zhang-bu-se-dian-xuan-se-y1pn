from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, FiniteFloat, StringConstraints

class RecordSwatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    family: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    fraction: FiniteFloat
    ground_l: FiniteFloat
    delta_e: FiniteFloat
    sample_ref: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    dry_hours: int


class WitnessSwatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chip: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


# 新操作的入参刻意宽松：现场可能按凭证号或干样编号发起，命名别名全部接住。
class WithdrawRef(BaseModel):
    model_config = ConfigDict(extra="allow")
    ref: Optional[str] = None
    sample_ref: Optional[str] = None
    voucher: Optional[str] = None
    voucher_ref: Optional[str] = None
    credential: Optional[str] = None
    ref_code: Optional[str] = None
    code: Optional[str] = None
    chip: Optional[str] = None
    swatch: Optional[str] = None
    swatch_code: Optional[str] = None
    sample_code: Optional[str] = None
    target: Optional[str] = None
    id: Optional[str] = None
    reason: Optional[str] = None
    note: Optional[str] = None
    comment: Optional[str] = None


class RetestSwatch(BaseModel):
    model_config = ConfigDict(extra="allow")
    chip: Optional[str] = None
    code: Optional[str] = None
    swatch_code: Optional[str] = None
    sample_code: Optional[str] = None
    ref: Optional[str] = None
    sample_ref: Optional[str] = None
    voucher: Optional[str] = None
    # 新读数（更正后的干样 ΔE76）
    delta_e: Optional[FiniteFloat] = None
    new_delta_e: Optional[FiniteFloat] = None
    observed_de: Optional[FiniteFloat] = None
    de: Optional[FiniteFloat] = None
    ground_l: Optional[FiniteFloat] = None
    fraction: Optional[FiniteFloat] = None
    dry_hours: Optional[int] = None
    new_ref: Optional[str] = None
    new_sample_ref: Optional[str] = None
    replacement_ref: Optional[str] = None
    witness: Optional[bool] = None
    witnessed: Optional[bool] = None
    verify: Optional[bool] = None
    verified: Optional[bool] = None

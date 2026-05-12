from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------- common ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


# ---------- profile ----------
class UserBase(BaseModel):
    username: str
    name: str
    email: str
    role: Literal["admin", "operator", "viewer"]
    enabled: bool = True


class UserOut(UserBase):
    id: str
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[Literal["admin", "operator", "viewer"]] = None
    enabled: Optional[bool] = None


class LoginIn(BaseModel):
    username: str
    password: str


# ---------- server ----------
class ServerLocation(BaseModel):
    idc: str
    rack: str
    u_position: str = Field(..., alias="uPosition")

    class Config:
        populate_by_name = True


class ServerBase(BaseModel):
    hostname: str
    sn: str
    asset_tag: str = Field(..., alias="assetTag")
    manufacturer: str
    model: str
    cpu_model: str = Field(..., alias="cpuModel")
    cpu_count: int = Field(..., alias="cpuCount")
    memory_gb: int = Field(..., alias="memoryGB")
    disk_count: int = Field(..., alias="diskCount")
    location: ServerLocation
    mgmt_ip: str = Field(..., alias="mgmtIp")
    biz_ip: str = Field(..., alias="bizIp")
    bmc_protocol: Literal["redfish", "ipmi"] = Field(..., alias="bmcProtocol")
    bmc_user: str = Field(..., alias="bmcUser")
    status: Literal["online", "offline", "maintenance", "retired"]
    owner: str
    purchase_date: Optional[date] = Field(None, alias="purchaseDate")
    warranty_end: Optional[date] = Field(None, alias="warrantyEnd")
    tags: list[str] = []
    remark: Optional[str] = None

    class Config:
        populate_by_name = True


class ServerOut(ServerBase):
    id: str
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")


# ---------- part ----------
class PartBase(BaseModel):
    category: Literal["disk", "memory", "nic", "optical", "other"]
    brand: str
    model: str
    spec: str
    sn: Optional[str] = None
    stock: int = 0
    safety_stock: int = Field(0, alias="safetyStock")
    unit: str = "块"
    location: str
    status: Literal["in_stock", "allocated", "in_use", "scrapped"] = "in_stock"
    remark: Optional[str] = None

    class Config:
        populate_by_name = True


class PartOut(PartBase):
    id: str
    created_at: datetime = Field(..., alias="createdAt")


# ---------- movement ----------
class MovementIn(BaseModel):
    part_id: str = Field(..., alias="partId")
    type: Literal["inbound", "outbound", "return", "scrap"]
    quantity: int
    operator: str
    related_server_id: Optional[str] = Field(None, alias="relatedServerId")
    reason: str

    class Config:
        populate_by_name = True


class MovementOut(BaseModel):
    id: str
    part_id: str = Field(..., alias="partId")
    part_model: str = Field(..., alias="partModel")
    category: str
    type: str
    quantity: int
    operator: str
    related_server_id: Optional[str] = Field(None, alias="relatedServerId")
    related_server_hostname: Optional[str] = Field(None, alias="relatedServerHostname")
    reason: str
    time: datetime

    class Config:
        populate_by_name = True


# ---------- audit ----------
class AuditOut(BaseModel):
    id: str
    time: datetime
    actor: str
    action: str
    target: str
    detail: str = ""
    level: Literal["info", "warn", "danger"]


# ---------- bmc ----------
class FanReading(BaseModel):
    name: str
    rpm: int
    status: Literal["OK", "Warning", "Critical"]


class PsuReading(BaseModel):
    name: str
    watts: int
    capacity_w: int = Field(..., alias="capacityW")
    status: Literal["OK", "Warning", "Critical"]

    class Config:
        populate_by_name = True


class AlertItem(BaseModel):
    id: str
    time: datetime
    level: Literal["OK", "Warning", "Critical"]
    message: str


class HistoryPoint(BaseModel):
    t: str
    cpu: float
    inlet: float
    power: float


class BmcStatus(BaseModel):
    server_id: str = Field(..., alias="serverId")
    power: Literal["On", "Off"]
    health: Literal["OK", "Warning", "Critical"]
    boot_progress: str = Field(..., alias="bootProgress")
    cpu_temp_c: float = Field(..., alias="cpuTempC")
    inlet_temp_c: float = Field(..., alias="inletTempC")
    fans: list[FanReading]
    psus: list[PsuReading]
    alerts: list[AlertItem]
    history: list[HistoryPoint]
    updated_at: datetime = Field(..., alias="updatedAt")

    class Config:
        populate_by_name = True


Token.model_rebuild()

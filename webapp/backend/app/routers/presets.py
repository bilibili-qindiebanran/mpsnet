"""训练超参数预设接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Preset
from ..schemas import PresetIn, PresetOut
from ..services import train_service

router = APIRouter(prefix="/api/presets", tags=["presets"])


@router.get("")
def list_presets(db: Session = Depends(get_db)):
    items = db.query(Preset).order_by(Preset.id.desc()).all()
    return {
        "total": len(items),
        "items": [PresetOut.model_validate(i).model_dump() for i in items],
    }


@router.post("", response_model=PresetOut)
def create_preset(payload: PresetIn, db: Session = Depends(get_db)):
    if db.query(Preset).filter(Preset.name == payload.name).first():
        raise HTTPException(400, f"预设名称已存在：{payload.name}")
    preset = Preset(
        name=payload.name,
        description=payload.description,
        params=train_service.sanitize_params(payload.params),
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return preset


@router.put("/{preset_id}", response_model=PresetOut)
def update_preset(preset_id: int, payload: PresetIn, db: Session = Depends(get_db)):
    preset = db.get(Preset, preset_id)
    if preset is None:
        raise HTTPException(404, "预设不存在")
    clash = db.query(Preset).filter(Preset.name == payload.name, Preset.id != preset_id).first()
    if clash:
        raise HTTPException(400, f"预设名称已存在：{payload.name}")
    preset.name = payload.name
    preset.description = payload.description
    preset.params = train_service.sanitize_params(payload.params)
    db.commit()
    db.refresh(preset)
    return preset


@router.delete("/{preset_id}")
def delete_preset(preset_id: int, db: Session = Depends(get_db)):
    preset = db.get(Preset, preset_id)
    if preset is None:
        raise HTTPException(404, "预设不存在")
    db.delete(preset)
    db.commit()
    return {"ok": True}

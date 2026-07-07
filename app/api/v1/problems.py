"""题目 CRUD（仅基础 POST/GET，OCR 入库在 P1.1 做）。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.problem import Problem
from app.schemas.problem import ProblemCreate, ProblemOut

router = APIRouter()


@router.post("/problems", response_model=ProblemOut, status_code=201)
def create_problem(req: ProblemCreate, db: Session = Depends(get_db)) -> ProblemOut:
    if db.query(Problem).filter(Problem.problem_id == req.problem_id).first():
        raise HTTPException(status_code=409, detail="problem_id already exists")
    p = Problem(
        problem_id=req.problem_id,
        title=req.title,
        description=req.description,
        difficulty=req.difficulty,
        input_format=req.input_format,
        output_format=req.output_format,
        examples_json=json.dumps(req.examples, ensure_ascii=False),
        constraints=req.constraints,
        reference_solution=req.reference_solution,
        test_cases_json=json.dumps(req.test_cases, ensure_ascii=False),
        scoring_rules_json=json.dumps(req.scoring_rules, ensure_ascii=False),
        source_book=req.source_book,
        source_chapter=req.source_chapter,
        source_page=req.source_page,
        ocr_raw=req.ocr_raw,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.get("/problems/{problem_id}", response_model=ProblemOut)
def get_problem(problem_id: str, db: Session = Depends(get_db)) -> ProblemOut:
    p = db.query(Problem).filter(Problem.problem_id == problem_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="problem not found")
    return _to_out(p)


def _to_out(p: Problem) -> ProblemOut:
    return ProblemOut(
        problem_id=p.problem_id,
        title=p.title,
        description=p.description,
        difficulty=p.difficulty,
        input_format=p.input_format,
        output_format=p.output_format,
        examples=json.loads(p.examples_json or "[]"),
        constraints=p.constraints,
        reference_solution=p.reference_solution,
        test_cases=json.loads(p.test_cases_json or "[]"),
        scoring_rules=json.loads(p.scoring_rules_json or "{}"),
        source_book=p.source_book,
        source_chapter=p.source_chapter,
        source_page=p.source_page,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )

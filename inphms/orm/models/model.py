from __future__ import annotations
import typing as t

from .basemodel import BaseModel

AbstractModel = BaseModel

class Model(AbstractModel):
    """ Main super-class for regular database-persisted Inphms models. """
    _auto: bool = True                   # automatically create database backend
    _register: bool = False              # not visible in ORM registry, meant to be python-inherited only
    _abstract: t.Literal[False] = False  # not abstract

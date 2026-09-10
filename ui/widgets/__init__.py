# -*- coding: utf-8 -*-
"""
PipeAgent — Reusable Widgets Package
=====================================
Exposes the master reusable UI components used across all PipeAgent tabs,
dashboards, and dialogs.

Version : 5.3.0
Engine  : PyQt6
"""
from __future__ import annotations

# ── Reusable widgets ────────────────────────────────────────
from .search_bar import SearchBar
from .stat_card import (
    StatCard,
    THEME_CYAN,
    THEME_LIGHT,
    THEME_GREEN,
    THEME_AMBER,
    THEME_RED,
    THEME_PURPLE,
)
from .status_tag import StatusTag, SEMANTIC_STYLES


__all__ = [
    "SearchBar",
    "StatCard",
    "StatusTag",
    "SEMANTIC_STYLES",
    # Theme accents
    "THEME_CYAN",
    "THEME_LIGHT",
    "THEME_GREEN",
    "THEME_AMBER",
    "THEME_RED",
    "THEME_PURPLE",
]
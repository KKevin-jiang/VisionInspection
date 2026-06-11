---
name: find-skill
description: 'Find files, symbols, text, recipes, ROI settings, PLC config, and implementation entry points in this workspace. Use when searching code, docs, JSON recipes, or locating where a behavior is implemented.'
argument-hint: 'What to find, such as file name, symbol, config field, behavior, or keyword'
user-invocable: true
---

# Find Skill

## What It Does
This skill provides a repeatable workflow for locating code, documents, recipe JSON, and implementation entry points in the current workspace.

It is intended for tasks such as:
- finding a file by name or path fragment
- finding a symbol or method implementation
- finding where a config field is read or written
- finding recipe, ROI, PLC, camera, or inspection logic
- finding related documentation before editing code

## When To Use
Use this skill when you need to find any of the following:
- Python source files in `vision_inspection`
- recipe JSON under `vision_inspection/data/recipes`
- ROI, binary threshold, or inspection algorithm configuration
- PLC, camera, workflow, or UI entry points
- references to a function, class, field, or keyword

Typical trigger phrases:
- find file
- find symbol
- locate implementation
- search recipe
- search ROI setting
- where is this handled
- where is this config used

## Procedure
1. Identify the search target type:
   - file name or path
   - exact text or keyword
   - symbol name
   - behavior description
2. Prefer the narrowest search first:
   - file search for names and paths
   - text search for exact config keys, strings, and keywords
   - semantic or symbol lookup for behavior and implementation points
3. If multiple results appear, narrow by area:
   - `vision_inspection/` for app code
   - `docs/` for design and requirements
   - `vision_inspection/data/recipes/` for live recipe configuration
4. Read the smallest relevant local slice before moving outward.
5. If the target is still ambiguous, compare only the closest candidate files and stop once the controlling code path is found.

## Search Heuristics
- For recipe fields, check both Python model definitions and JSON recipe files.
- For UI behavior, start in `vision_inspection/ui/` and then follow controller or service calls.
- For inspection behavior, start in `vision_inspection/infrastructure/vision/` and `vision_inspection/application/services/`.
- For PLC flow, start in `vision_inspection/application/controllers/`, `vision_inspection/application/services/`, and `vision_inspection/infrastructure/plc/`.
- For camera flow, start in `vision_inspection/application/controllers/`, `vision_inspection/application/services/`, and `vision_inspection/infrastructure/camera/`.

## Output Expectations
A successful search should return:
- the most relevant file path
- the likely owning function, class, or config surface
- the next best adjacent file only if needed

## Scope
This skill is workspace-scoped and installed at `.github/skills/find-skill/SKILL.md`.

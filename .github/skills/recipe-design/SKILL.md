---
name: recipe-design
description: 'Design recipe workflows, template management, ROI editing, parameter configuration, binary threshold setup, inspection configuration pages, and operator-friendly recipe editing for vision software. Use when planning recipe structures, template/ROI UX, or parameter editing flows.'
argument-hint: 'What recipe or ROI interface/workflow to design'
user-invocable: true
---

# Recipe Design

## What It Does
This skill helps design recipe-centric interfaces and workflows for inspection software.

It is best for:
- recipe creation and editing flows
- template and ROI management UX
- binary threshold and inspection parameter configuration
- reducing confusion in parameter-heavy recipe editors
- separating operator usage from engineering configuration

## When To Use
Use this skill when the task involves:
- 配方设计
- 配方编辑界面
- ROI 编辑流程
- 模板管理流程
- 检测参数配置
- 二值化参数设置流程
- 配方复制、新建、保存、切换流程

Typical triggers:
- design recipe editor
- improve ROI workflow
- simplify recipe settings
- design threshold configuration
- redesign parameter editing

## Core Principles
1. Basic recipe information should be separate from template-specific settings.
2. ROI selection, image context, and ROI parameter editing should stay tightly linked.
3. Avoid raw JSON editing unless it is explicitly an advanced mode.
4. Parameter workflows should start from presets or templates when possible.
5. Editing should preserve visual context and current selection.
6. High-frequency actions should be obvious; risky actions should be explicit.

## Recommended Recipe Editor Structure
1. Basic Info
   - recipe id
   - recipe name
   - product / station / camera
   - enable state
2. Template and ROI
   - template selection
   - template image view
   - ROI draw/select/delete
   - ROI list
3. Inspection Parameters
   - algorithm selection
   - threshold tuning
   - binary parameter visualization
   - presets
4. PLC and Runtime
   - trigger settings
   - NG output settings
   - timing and retry rules
5. Storage and Traceability
   - save options
   - retention
   - result record behavior

## ROI Workflow Guidance
1. Select ROI from image or table.
2. Show the selected ROI clearly.
3. Keep ROI parameter editing next to the visual region.
4. Provide immediate visual feedback for threshold-based settings.
5. Show readable summaries instead of raw parameter blobs.

## Output Expectations
A good response using this skill should provide:
- recommended page or dialog structure
- workflow sequence for create/edit/save
- separation of basic vs advanced settings
- ROI interaction design
- usability rationale tied to inspection work

## Scope
This skill is workspace-scoped and installed at `.github/skills/recipe-design/SKILL.md`.

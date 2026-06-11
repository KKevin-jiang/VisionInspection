---
name: software-ui-design
description: 'Design desktop software UI, PyQt interfaces, industrial HMI screens, recipe editor pages, ROI workflow, operator screens, status panels, and configuration dialogs. Use when planning software interface structure, interaction flow, page layout, control grouping, or usability improvements for desktop applications.'
argument-hint: 'What interface to design, such as main window, recipe editor, parameter dialog, operator page, or workflow'
user-invocable: true
---

# Software UI Design

## What It Does
This skill helps design desktop software interfaces, especially PyQt-based business tools, industrial operator screens, inspection software, parameter dialogs, and workflow-oriented configuration pages.

It is suited for tasks such as:
- designing a main application window
- designing a recipe editor or parameter page
- designing a binary-threshold configuration dialog
- improving operator usability and reducing training cost
- reorganizing controls, status information, and workflows
- designing interface structures before implementation

## Best Fit
Use this skill when the target is a desktop software interface rather than a website.

This skill is particularly useful for:
- PyQt5 or PySide desktop applications
- industrial vision inspection software
- HMI-like operator screens
- configuration dialogs with many parameters
- workflows that combine image view, ROI, results, and settings

## When To Use
Use this skill when the user asks for any of the following:
- 软件界面设计
- 主界面规划
- 配方编辑界面
- 参数设置页面
- 对话框优化
- 操作流程优化
- 可视化设置流程
- 操作员页面设计
- UI 布局建议
- 工业软件界面规范

Typical trigger phrases:
- design the UI
- design the interface
- improve the dialog
- layout the main window
- redesign the editor
- operator-friendly workflow
- desktop UI planning

## Design Principles
1. Prioritize task flow over visual decoration.
2. Keep operator actions obvious and low-risk.
3. Separate runtime actions from configuration actions.
4. Group controls by workflow stage, not by implementation detail.
5. Keep critical status always visible.
6. Reduce hidden states and ambiguous controls.
7. Prefer direct manipulation where possible, such as ROI drawing on images.
8. Use confirmations only for risky operations.
9. Make parameter-heavy dialogs progressively discoverable.
10. Favor clear labels and predictable placement over novelty.

## Recommended Workflow
1. Identify the user role:
   - operator
   - technician
   - engineer
   - administrator
2. Identify the interface type:
   - main window
   - editor page
   - settings dialog
   - monitoring panel
   - result review page
3. Identify the primary task sequence:
   - load recipe
   - capture image
   - inspect
   - review result
   - adjust parameters
   - save
4. Define which information must remain visible at all times.
5. Split controls into primary, secondary, and advanced groups.
6. Design layout regions before individual widgets.
7. Validate that the UI reduces operator confusion and accidental misuse.

## Layout Guidance
### Main Window
For inspection software, prefer a stable 3-zone structure:
1. Top bar:
   - current recipe
   - start/stop actions
   - mode switches
   - communication status
2. Main image area:
   - current image
   - ROI overlays
   - result overlays
3. Right or lower side panel:
   - overall result
   - ROI result list
   - alarms and recent errors
   - recipe and device summary

### Parameter or Configuration Dialogs
For parameter-heavy dialogs:
1. Put the visual target on one side.
2. Put the editable parameters on the other side.
3. Show live feedback whenever possible.
4. Add concise field explanations near advanced parameters.
5. Use presets or templates to reduce blank-start confusion.

### Recipe Editors
For recipe editing:
1. Separate basic recipe metadata from template-specific settings.
2. Keep ROI selection and ROI parameter editing tightly linked.
3. Avoid forcing users to edit raw JSON when a structured editor is possible.
4. Show current selection clearly.
5. Preserve image context while editing ROI-related parameters.

## Industrial UI Heuristics
- Keep machine and PLC state visible.
- Make NG causes easy to read.
- Prefer large, high-contrast result indicators.
- Prevent operators from accidentally entering engineering settings.
- Distinguish manual test actions from production-triggered actions.
- Keep error messages actionable.
- Use wording operators understand, not internal developer terminology.

## Output Expectations
A good response using this skill should provide:
- the target screen or dialog structure
- grouped controls by workflow
- interaction sequence
- usability rationale
- implementation direction when needed

## Scope
This skill is workspace-scoped and installed at `.github/skills/software-ui-design/SKILL.md`.

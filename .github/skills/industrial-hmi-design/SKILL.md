---
name: industrial-hmi-design
description: 'Design industrial HMI screens, operator panels, machine status views, alarm regions, PLC/device status displays, and production-safe desktop interfaces. Use when planning operator-facing industrial software or runtime monitoring screens.'
argument-hint: 'What industrial screen, operator page, or monitoring interface to design'
user-invocable: true
---

# Industrial HMI Design

## What It Does
This skill helps design industrial operator-facing interfaces for runtime use.

It is suited for:
- machine status screens
- operator main windows
- production runtime dashboards
- PLC and camera state presentation
- alarm and fault display regions
- permission-aware control layouts

## When To Use
Use this skill when the task involves:
- 工业 HMI 设计
- 操作员主界面
- 设备状态监控页面
- 报警区设计
- 产线运行界面
- PLC/相机状态显示
- 手动测试与自动运行界面区分

Typical triggers:
- design operator screen
- design HMI
- improve runtime interface
- redesign status panel
- machine state UI
- alarm layout

## Core Principles
1. Running state must be visible at all times.
2. Alarm state must be impossible to miss.
3. Manual actions must be clearly separated from automatic production flow.
4. Device and communication state must be readable without opening dialogs.
5. Operator screens should minimize engineering complexity.
6. Critical actions should be large, stable, and predictable.

## Recommended Runtime Layout
1. Header area
   - current recipe
   - machine mode
   - user role
   - current time / batch context
2. Main center area
   - live image or inspection view
   - ROI/result overlay
3. Result area
   - OK/NG state
   - failed region list
   - last cycle result
4. Status area
   - PLC state
   - camera state
   - trigger state
   - save state
5. Alarm / error area
   - active fault
   - recent errors
   - operator action guidance
6. Action area
   - start / stop
   - reset alarm
   - manual capture
   - manual test

## Operator Safety Guidance
- Distinguish monitoring controls from engineering settings.
- Use confirmations for destructive or production-affecting actions.
- Keep emergency or stop-related controls isolated and visible.
- Do not bury active errors inside tabs.

## Output Expectations
A good response using this skill should provide:
- recommended HMI structure
- visible state hierarchy
- alarm and status presentation guidance
- operator action layout
- rationale for production safety and clarity

## Scope
This skill is workspace-scoped and installed at `.github/skills/industrial-hmi-design/SKILL.md`.

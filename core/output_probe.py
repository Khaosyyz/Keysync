"""Output-layer capability probe (UI Automation).

Decides whether the focused UI element can accept text:

  opaque-native-window (ControlType=Window, self-drawn UI like WeChat)
        -> treat as input-capable (UIA cannot see inside, injection still works)
  Edit(50004)
        -> input-capable
  Document(50030)
        -> input-capable only when ValueIsReadOnly == False (real editing surface,
           not a page body you merely clicked on)
  anything else / disabled
        -> not input-capable
"""
import ctypes

import comtypes.client
comtypes.client.GetModule("UIAutomationCore.dll")
import comtypes.gen.UIAutomationClient as uia

CT_EDIT = uia.UIA_EditControlTypeId
CT_DOCUMENT = uia.UIA_DocumentControlTypeId
CT_WINDOW = uia.UIA_WindowControlTypeId


class ProbeResult:
    __slots__ = ("can_input", "reason", "control_type", "name", "class_name", "read_only")

    def __init__(self, can_input, reason, control_type=None, name="", class_name="",
                 read_only=None):
        self.can_input = can_input
        self.reason = reason
        self.control_type = control_type
        self.name = name
        self.class_name = class_name
        self.read_only = read_only

    def __repr__(self):
        return (f"ProbeResult(can_input={self.can_input}, reason={self.reason!r}, "
                f"ct={self.control_type}, read_only={self.read_only}, name={self.name[:24]!r})")


class FocusProbe:
    def __init__(self):
        ctypes.windll.ole32.CoInitializeEx(None, 0x0)
        self._uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=uia.IUIAutomation)

    def probe(self) -> ProbeResult:
        try:
            element = self._uia.GetFocusedElement()
        except Exception as exc:
            return ProbeResult(False, f"GetFocusedElement failed: {exc}")
        if element is None:
            return ProbeResult(False, "no focused element")

        try:
            ct = element.GetCurrentPropertyValue(uia.UIA_ControlTypePropertyId)
            name = str(element.GetCurrentPropertyValue(uia.UIA_NamePropertyId) or "")
            cls = str(element.GetCurrentPropertyValue(uia.UIA_ClassNamePropertyId) or "")
            enabled = bool(element.GetCurrentPropertyValue(uia.UIA_IsEnabledPropertyId))
            read_only = element.GetCurrentPropertyValue(uia.UIA_ValueIsReadOnlyPropertyId)
        except Exception as exc:
            return ProbeResult(False, f"property read failed: {exc}")

        if not enabled:
            return ProbeResult(False, "focused element is disabled", ct, name, cls, read_only)

        if ct == CT_WINDOW:
            return ProbeResult(True, "opaque native window (UIA cannot see inside)",
                               ct, name, cls, read_only)

        if ct == CT_EDIT:
            return ProbeResult(True, "Edit control", ct, name, cls, read_only)

        if ct == CT_DOCUMENT:
            if read_only is False:
                return ProbeResult(True, "Document, editable", ct, name, cls, read_only)
            return ProbeResult(False, "Document, read-only (no caret)", ct, name, cls, read_only)

        return ProbeResult(False, f"ControlType={ct} is not a text input type",
                           ct, name, cls, read_only)

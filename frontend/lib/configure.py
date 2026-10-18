"""The configuration panel, beside the controls that run the stage.

Drawn inside the page's service panel, where the Redo button that rebuilds
what a change staled already is.

Every control is derived from what the API says about the setting - its
type, its bounds, the closed set of values where there is one - so there is
no list of settings here.

Collapsed by default.
"""

from __future__ import annotations

from typing import Any

import requests
import streamlit as st

from lib import backend
from lib.backend.base import refusal

#: How a flag is written back. Everything goes to the API as text.
_TRUE, _FALSE = "true", "false"

#: Where a message waits out the rerun that a save causes.
_SAID = "settings-said-{service}"

#: The version the panel was drawn from, which a save is sent against.
_DRAWN = "settings-drawn-{service}"

#: Each control's key. The version in it: a widget keyed on its name alone
#: keeps the value it was first drawn with whatever the API says afterwards.
_KEY = "setting-{service}-{name}-{version}"


def panel(service: str) -> None:
    """Draws one service's configuration, inside the panel that runs it.

    Builds its own client: two of the pages that draw this hold no other.
    """
    client = backend.settings_api()
    try:
        held = client.settings(service)
    except requests.exceptions.RequestException as error:
        st.caption(f"Configuration unavailable: {refusal(error)}")
        return
    # Kept until a save is tried, so a change made elsewhere meanwhile is
    # the API's 409 rather than silently undone. Taken again once no control
    # drawn from it is left, as after a visit to another page: the controls
    # are then drawn from what the API holds now, and the version is global,
    # so a save on that page would refuse the next one here for nothing.
    drawn = _DRAWN.format(service=service)
    version = st.session_state.get(drawn)
    if not any(
        _KEY.format(service=service, name=one["name"], version=version)
        in st.session_state
        for one in held["settings"]
    ):
        st.session_state[drawn] = held["version"]
    held = {**held, "version": st.session_state[drawn]}

    changed = sum(one["stored"] for one in held["settings"])
    label = "Configuration" + (f" · {changed} changed" if changed else "")
    with st.expander(label):
        _form(client, service, held)
        if changed:
            _reset(client, service, held)

    # Outside the fold, so it is read without opening the panel again.
    said = st.session_state.pop(_SAID.format(service=service), None)
    if said:
        st.warning(said)


def _form(client, service: str, held: dict) -> None:
    """Draws the settings as a form, and saves what it is submitted with."""
    with st.form(f"settings-{service}", border=False):
        values: dict[str, str | None] = {}
        for setting in held["settings"]:
            drawn = _control(service, setting, held["version"])
            if drawn is not None:
                values[setting["name"]] = drawn
        submitted = st.form_submit_button("Save", type="primary")

    if submitted:
        _save(client, service, values, held["version"])


def _reset(client, service: str, held: dict) -> None:
    """Offers to return every changed setting to what the files say."""
    stored = [one["name"] for one in held["settings"] if one["stored"]]
    if st.button(
        "Return to the file",
        key=f"reset-{service}",
        help=f"Deletes the {len(stored)} stored value(s), so "
        f"configs/env/backend.env and .env decide again.",
    ):
        _save(client, service, dict.fromkeys(stored), held["version"])


def _save(client, service: str, values: dict[str, str | None], version: str) -> None:
    """Sends one change and says what it did, or why it was refused."""
    # Whatever the answer, the next run draws what the API holds then.
    st.session_state.pop(_DRAWN.format(service=service), None)
    try:
        answer = client.change_settings(service, values, version)
    except requests.exceptions.RequestException as error:
        st.error(refusal(error))
        return

    st.toast(answer.get("detail") or f"{service}: settings saved")
    moved = answer.get("changed") or answer.get("cleared")
    if answer.get("stale"):
        # Held, not drawn: it has to outlive the rerun below.
        st.session_state[_SAID.format(service=service)] = answer["detail"]
    if moved:
        st.rerun(scope="app")


def _control(service: str, setting: dict, version: str) -> str | None:
    """Draws one setting's control, and reads back what it holds as text.

    Returns None for a setting the deployment owns, which is drawn disabled
    and never written.
    """
    key = _KEY.format(service=service, name=setting["name"], version=version)
    value = setting["value"]
    label = _label(setting)
    help = _help(setting)

    if setting["fixed"]:
        st.text_input(label, value=value or "", key=key, help=help, disabled=True)
        return None

    if setting["kind"] == "boolean":
        return (
            _TRUE
            if st.checkbox(label, value=_flag(value), key=key, help=help)
            else _FALSE
        )

    if setting["choices"]:
        return _chosen(setting, label, key, help)

    if setting["optional"]:
        # Typed by hand even for a number: a number box cannot say nothing,
        # and an empty box is how one is turned off.
        return st.text_input(label, value=value or "", key=key, help=help)

    if setting["kind"] == "integer":
        return str(
            int(
                _number(
                    setting,
                    int(value or 0),
                    int,
                    label=label,
                    step=1,
                    key=key,
                    help=help,
                )
            )
        )

    if setting["kind"] == "decimal":
        places = max(2, len((value or "").partition(".")[2]))
        drawn = _number(
            setting,
            float(value or 0),
            float,
            label=label,
            step=10.0**-places,
            format=f"%0.{places}f",
            key=key,
            help=help,
        )
        # Untouched goes back as the API wrote it: "0.3" for "0.30" is a
        # different string, and the API stores a different string.
        return value if value and float(value) == drawn else _written(drawn)

    return st.text_input(label, value=value or "", key=key, help=help)


def _number(setting: dict, held: float, kind: type, **drawn: Any) -> Any:
    """Draws a number box held to the setting's bounds, if it lies inside them.

    One stored before a bound moved past it is drawn without them and said
    to be outside them: drawn with them, Streamlit raises, and the page fails
    with the panel that could correct it.
    """
    low, high = _bound(setting["low"], kind), _bound(setting["high"], kind)
    outside = (low is not None and held < low) or (high is not None and held > high)
    number = st.number_input(
        value=held,
        min_value=None if outside else low,
        max_value=None if outside else high,
        **drawn,
    )
    if outside:
        must = " and ".join(
            f"{word} {bound}"
            for word, bound in (("at least", low), ("at most", high))
            if bound is not None
        )
        st.warning(f"{setting['name']} holds {held}, but must be {must}.")
    return number


def _chosen(setting: dict, label: str, key: str, help: str) -> str | None:
    """Draws the control for a setting with a closed set of values."""
    choices = setting["choices"]
    if setting["kind"] in ("csv", "mapping"):
        held = [
            one.strip() for one in (setting["value"] or "").split(",") if one.strip()
        ]
        picked = st.multiselect(
            label,
            choices,
            default=[one for one in held if one in choices],
            key=key,
            help=help,
        )
        return ",".join(picked)

    # A blank first entry when absence means something.
    offered = ["", *choices] if setting["optional"] else list(choices)
    current = setting["value"] or ""
    # A value no longer offered is drawn as the default, not as whichever
    # choice comes first: the form sends every value, so Save would store it.
    if current not in offered:
        current = setting["default"] or ""
    # Neither is offered: drawn blank and sent only once something is picked.
    unoffered = current not in offered
    if unoffered:
        offered = offered if "" in offered else ["", *offered]
        current = ""
    # `or ""`: nothing chosen reads as absent.
    picked = (
        st.selectbox(label, offered, index=offered.index(current), key=key, help=help)
        or ""
    )
    return None if unoffered and not picked else picked


def _label(setting: dict) -> str:
    """The setting's name, marked when the files no longer decide it."""
    return f"{setting['name']} ·" if setting["stored"] else setting["name"]


def _help(setting: dict) -> str:
    """What the setting does, and what changing it leaves behind."""
    said = setting["help"]
    if setting["fixed"]:
        said = f"{said} Set in .env; changing it needs a restart."
    if setting["stored"]:
        said = f"{said} Changed from {setting['default'] or 'unset'}."
    if setting["invalidates"]:
        said = (
            f"{said} What {', '.join(setting['invalidates'])} already produced "
            f"was made under the current value."
        )
    return said


def _flag(value: str | None) -> bool:
    """Reads a stored flag the way the backend's own reader reads it."""
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _bound(value: Any, kind: type) -> Any:
    """One bound, in the type its control wants, or nothing."""
    return None if value is None else kind(value)


def _written(value: float) -> str:
    """Writes a number back without the trailing zeros a widget adds."""
    return f"{value:g}"

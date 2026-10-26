# -*- coding: utf-8 -*-
r"""RCAIDE-GUI 离屏冒烟 / 截图 / 控件树导出 (offscreen smoke test).

用法:
    python gui_smoke.py capture
    python gui_smoke.py capture --load Cessna_172
    python gui_smoke.py simulate --load Cessna_172

输出: D:\RCAIDE\outputs\gui\*.png 与 D:\RCAIDE\checks\gui-2026-10-21\*.json
"""
import os
import sys
import json
import time
import traceback
import argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_IMG = r"D:\RCAIDE\outputs\gui"
OUT_JSON = HERE
SP = r"D:\RCAIDE\envs\RCAIDE\Lib\site-packages"

log_lines = []
def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg, flush=True)
    log_lines.append(msg)

def flush_log(name="gui_smoke.log"):
    with open(os.path.join(OUT_JSON, name), "a", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    log_lines.clear()

def env_report():
    import platform
    info = {
        "python": sys.version.replace("\n", " "),
        "executable": sys.executable,
        "platform": platform.platform(),
        "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM"),
        "site_packages": SP,
    }
    for mod in ("PyQt6.QtCore", "RCAIDE", "pyqtgraph", "pyvista", "pyvistaqt", "vtk", "matplotlib", "numpy"):
        try:
            m = __import__(mod, fromlist=["__version__"])
            info[mod] = str(getattr(m, "__version__", getattr(m, "__file__", "?")))
        except Exception as e:
            info[mod] = "IMPORT-FAIL: %r" % (e,)
    try:
        import importlib.metadata as md
        for pkg in ("rcaide-gui", "RCAIDE-LEADS", "PyQt6"):
            try:
                info[pkg] = md.version(pkg)
            except Exception as e:
                info[pkg] = "n/a (%s)" % e
    except Exception:
        pass
    return info

SKIP_TEXT_TYPES = ("QScrollBar",)

def widget_text(w):
    out = {}
    cls = type(w).__name__
    try:
        if hasattr(w, "text") and callable(w.text):
            t = w.text()
            if isinstance(t, str) and t.strip():
                out["text"] = t.strip()[:200]
    except Exception:
        pass
    try:
        if hasattr(w, "placeholderText") and callable(w.placeholderText):
            t = w.placeholderText()
            if t:
                out["placeholder"] = t[:120]
    except Exception:
        pass
    try:
        if hasattr(w, "currentText") and hasattr(w, "count") and hasattr(w, "itemText"):
            out["items"] = [w.itemText(i) for i in range(min(w.count(), 60))]
            out["current"] = w.currentText()
    except Exception:
        pass
    try:
        if hasattr(w, "topLevelItemCount") and hasattr(w, "topLevelItem"):
            out["header"] = [w.headerItem().text(c) for c in range(w.columnCount())]
            out["topLevelCount"] = w.topLevelItemCount()
            out["topLevel"] = [w.topLevelItem(i).text(0) for i in range(min(w.topLevelItemCount(), 80))]
    except Exception:
        pass
    try:
        if hasattr(w, "rowCount") and hasattr(w, "columnCount"):
            out["dims"] = [w.rowCount(), w.columnCount()]
    except Exception:
        pass
    try:
        if hasattr(w, "title") and cls.endswith("GroupBox"):
            out["title"] = w.title()
    except Exception:
        pass
    try:
        if cls.endswith("TabWidget"):
            out["tabs"] = [w.tabText(i) for i in range(w.count())]
    except Exception:
        pass
    return out

def walk(w, depth=0, max_depth=40):
    node = {"cls": type(w).__name__}
    if w.objectName():
        node["name"] = w.objectName()
    node.update(widget_text(w))
    try:
        node["visible"] = w.isVisible()
        node["enabled"] = w.isEnabled()
    except Exception:
        pass
    try:
        g = w.geometry()
        node["geom"] = [g.x(), g.y(), g.width(), g.height()]
    except Exception:
        pass
    if type(w).__name__ in SKIP_TEXT_TYPES or depth >= max_depth:
        return node
    kids = []
    for c in list(w.children()):
        if not hasattr(c, "isWidgetType") or not c.isWidgetType():
            continue
        try:
            kids.append(walk(c, depth + 1, max_depth))
        except Exception as e:
            kids.append({"cls": type(c).__name__, "error": repr(e)})
    if kids:
        node["children"] = kids
    return node

def summarize_tree(node, acc=None):
    if acc is None:
        acc = {"type_counts": {}, "interactive": []}
    acc["type_counts"][node["cls"]] = acc["type_counts"].get(node["cls"], 0) + 1
    cls = node["cls"]
    if any(k in cls for k in ("QPushButton", "QComboBox", "QLineEdit", "QCheckBox", "QTreeWidget",
                              "QTableWidget", "QGroupBox", "QTabWidget", "QProgressDialog", "QSlider",
                              "QDoubleSpinBox", "QSpinBox", "QRadioButton")):
        entry = {"cls": cls}
        for k in ("name", "text", "title", "placeholder", "items", "current",
                  "header", "tabs", "dims"):
            if k in node:
                entry[k] = node[k]
        acc["interactive"].append(entry)
    for c in node.get("children", []):
        summarize_tree(c, acc)
    return acc

def pump(app, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        app.processEvents()
        time.sleep(0.02)

def capture_all(app, tabs, prefix):
    out = []
    for i in range(tabs.count()):
        name = tabs.tabText(i)
        safe = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_")
        tabs.setCurrentIndex(i)
        w = tabs.widget(i)
        pump(app, 0.45)
        try:
            if hasattr(w, "update_layout"):
                w.update_layout()
            pump(app, 0.35)
        except Exception as e:
            log("[WARN] update_layout failed on %r: %r" % (name, e))
        shot = os.path.join(OUT_IMG, "%s_%02d_%s.png" % (prefix, i + 1, safe))
        pm = None
        ok = False
        try:
            pm = w.grab()
            ok = pm.save(shot, "PNG")
        except Exception as e:
            log("[WARN] grab failed on %r: %r" % (name, e))
        tree = walk(w)
        sumry = summarize_tree(tree)
        jpath = os.path.join(OUT_JSON, "%s_%02d_%s.json" % (prefix, i + 1, safe))
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump({"tab_index": i, "tab_name": name, "tree": tree, "summary": sumry},
                      f, ensure_ascii=False, indent=1)
        rec = {"index": i, "name": name, "png": shot if ok else None, "json": jpath,
               "interactive_count": len(sumry["interactive"]),
               "type_counts": dict(sorted(sumry["type_counts"].items(), key=lambda kv: -kv[1])[:14])}
        if pm is not None:
            rec["png_size"] = [pm.width(), pm.height()]
        out.append(rec)
        log("[CAPTURE] #%d %-22s -> %s saved=%s interactive=%d" %
            (i + 1, name, os.path.basename(shot), ok, len(sumry["interactive"])))
    return out

def state_snapshot():
    import rcaide_io
    st = {}
    v = rcaide_io.vehicle
    st["vehicle_tag"] = getattr(v, "tag", None)
    for cat in ("wings", "fuselages", "booms", "cargo_bays", "landing_gears", "networks"):
        try:
            st[cat] = [getattr(x, "tag", "?") for x in getattr(v, cat, [])]
        except Exception as e:
            st[cat] = "err:%r" % (e,)
    try:
        st["reference_area"] = getattr(v, "reference_area", None)
        st["num_passengers"] = getattr(v, "number_of_passengers", None)
        mp = getattr(v, "mass_properties", None)
        st["mass"] = {"max_takeoff": getattr(mp, "max_takeoff", None),
                      "takeoff": getattr(mp, "takeoff", None),
                      "operating_empty": getattr(mp, "operating_empty", None)}
    except Exception:
        pass
    try:
        st["configs"] = [getattr(c, "tag", "?") for c in rcaide_io.rcaide_configs]
    except Exception as e:
        st["configs"] = "err:%r" % (e,)
    try:
        inner = {}
        for k, cont in rcaide_io.rcaide_analyses.items():
            try:
                inner[k] = [getattr(a, "tag", type(a).__name__) for a in cont]
            except Exception:
                inner[k] = str(type(cont))
        st["analyses"] = inner
    except Exception as e:
        st["analyses"] = "err:%r" % (e,)
    try:
        st["mission_data_segments"] = len(rcaide_io.mission_data)
        st["mission_data_tags"] = [s.get("Segment Name") or s.get("type") for s in rcaide_io.mission_data][:15]
    except Exception as e:
        st["mission_data_segments"] = "err:%r" % (e,)
    try:
        m = rcaide_io.rcaide_mission
        st["rcaide_mission_segments"] = [getattr(s, "tag", "?") for s in getattr(m, "segments", [])][:15]
    except Exception as e:
        st["rcaide_mission_segments"] = "err:%r" % (e,)
    return st

def close_modals():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    closed = []
    for _ in range(6):
        w = app.activeModalWidget()
        if w is None:
            break
        try:
            closed.append(w.windowTitle() or type(w).__name__)
            w.close()
        except Exception:
            break
    return closed

def pump_guard(app, seconds):
    t0 = time.time()
    closed = []
    while time.time() - t0 < seconds:
        app.processEvents()
        c = close_modals()
        if c:
            closed.extend(c)
        time.sleep(0.02)
    return closed

def find_button(root, substr):
    from PyQt6.QtWidgets import QPushButton
    for b in root.findChildren(QPushButton):
        try:
            if substr.lower() in b.text().lower():
                return b
        except Exception:
            continue
    return None

def gl_report():
    """Ask VTK for the OpenGL vendor/renderer strings actually in use."""
    out = {}
    try:
        import vtk
        out["vtk_version"] = vtk.vtkVersion.GetVTKVersion()
        rw = vtk.vtkOpenGLRenderWindow()
        rw.SetOffScreenRendering(1)
        rw.Render()
        try:
            out["gl_vendor"] = rw.ReportCapabilities().split("OpenGL vendor string:")[1].split("\n")[0].strip()
        except Exception:
            pass
        try:
            caps = rw.ReportCapabilities()
            for line in caps.splitlines():
                line = line.strip()
                if any(k in line for k in ("OpenGL Version", "OpenGL Renderer", "OpenGL Vendor",
                                           "OpenGL Version String", "Driver Version")):
                    out.setdefault("caps", []).append(line)
        except Exception:
            pass
        try:
            import pyvista
            out["pyvista_version"] = pyvista.__version__
        except Exception:
            pass
        rw.Finalize()
    except Exception:
        out["error"] = traceback.format_exc(limit=3)
    return out

def home_dropdown_load(app, tabs, win, aircraft_name):
    """Drive the real GUI path: Home tab -> example aircraft combo -> load_file."""
    from PyQt6.QtWidgets import QComboBox
    out = {"requested": aircraft_name}
    names = [tabs.tabText(i) for i in range(tabs.count())]
    home_idx = names.index("Home") if "Home" in names else 0
    tabs.setCurrentIndex(home_idx)
    pump_guard(app, 0.5)
    home = tabs.widget(home_idx)
    combo = None
    for c in home.findChildren(QComboBox):
        items = [c.itemText(i) for i in range(c.count())]
        if any("Load aircraft" in t for t in items):
            combo = c
            out["combo_item_count"] = c.count()
            out["combo_first_items"] = items[:6]
            break
    if combo is None:
        out["combo_found"] = False
        return out
    out["combo_found"] = True
    target = None
    for i in range(combo.count()):
        t = combo.itemText(i)
        if t.strip().lower().replace(" ", "_") == aircraft_name.lower() or \
           t.strip().lower().replace(" ", "").replace("_", "") == aircraft_name.lower().replace("_", ""):
            target = i
            break
    if target is None:
        for i in range(combo.count()):
            if aircraft_name.lower() in combo.itemText(i).lower().replace(" ", "_"):
                target = i
                break
    out["combo_index"] = target
    if target is None:
        out["error"] = "aircraft not present in Home dropdown"
        return out
    t0 = time.time()
    combo.setCurrentIndex(target)
    # _load_example runs load_file then resets the combo; pump until data arrives
    deadline = time.time() + 180
    import rcaide_io
    ok = False
    while time.time() < deadline:
        app.processEvents()
        close_modals()
        if rcaide_io.vehicle is not None and len(getattr(rcaide_io.vehicle, "wings", [])) > 0:
            ok = True
            break
        if time.time() - t0 > 5 and getattr(rcaide_io, "current_file_path", ""):
            ok = True
            break
        time.sleep(0.05)
    out["load_detected"] = ok
    out["seconds"] = round(time.time() - t0, 1)
    out["current_file_path"] = getattr(rcaide_io, "current_file_path", None)
    out["combo_reset_text"] = combo.currentText()
    return out

def summarize_results(results):
    res = {}
    try:
        segs = list(getattr(results, "segments", []))
        res["segment_count"] = len(segs)
        res["segment_tags"] = [getattr(s, "tag", "?") for s in segs]
        for i, s in enumerate(segs[:5]):
            d = {"tag": getattr(s, "tag", "?")}
            cond = getattr(s, "conditions", None)
            fs = getattr(cond, "freestream", None) if cond is not None else None
            if fs is not None:
                for attr in ("altitude", "velocity", "mach_number", "dynamic_pressure"):
                    try:
                        v = getattr(fs, attr)
                        d[attr] = float(v[0][0]) if hasattr(v[0], "__len__") else float(v[0])
                    except Exception:
                        pass
            fr = getattr(cond, "frames", None) if cond is not None else None
            w = getattr(fr, "weights", None) if fr is not None else None
            if w is not None:
                try:
                    d["weight_kg"] = float(w.total[0][0])
                except Exception:
                    pass
            res["segment_%d" % i] = d
    except Exception:
        res["summary_error"] = traceback.format_exc()
    return res

def do_simulate(win, app, tabs):
    import rcaide_io
    out = {}
    out["state_before"] = state_snapshot()
    names = [tabs.tabText(i) for i in range(tabs.count())]
    run_idx = names.index("Run Mission") if "Run Mission" in names else 7
    run_tab = tabs.widget(run_idx)
    btn = find_button(run_tab, "Simulate Mission")
    out["simulate_button_found"] = btn is not None
    m = rcaide_io.rcaide_mission
    segs = list(getattr(m, "segments", []))
    out["mission_segments"] = [getattr(s, "tag", "?") for s in segs]
    if not segs:
        out["evaluate_ok"] = False
        out["reason"] = "mission has no segments -> cannot simulate"
        return out
    t0 = time.time()
    try:
        results = m.evaluate()
        out["direct_evaluate_ok"] = True
        out["direct_evaluate_seconds"] = round(time.time() - t0, 1)
        rcaide_io.rcaide_results = results
        out["results"] = summarize_results(results)
    except Exception:
        out["direct_evaluate_ok"] = False
        out["direct_evaluate_seconds"] = round(time.time() - t0, 1)
        out["direct_evaluate_traceback"] = traceback.format_exc()
        log("[ERROR] direct evaluate failed:\n" + out["direct_evaluate_traceback"])
        return out
    try:
        if hasattr(run_tab, "render_solve_plots"):
            run_tab.render_solve_plots(results)
            pump_guard(app, 2.0)
            out["render_plots_ok"] = True
            out["dynamic_plot_widgets"] = len(getattr(run_tab, "_dynamic_plot_widgets", []))
    except Exception:
        out["render_plots_ok"] = False
        out["render_plots_traceback"] = traceback.format_exc()
    if btn is not None:
        try:
            tabs.setCurrentIndex(run_idx)
            pump_guard(app, 0.3)
            btn.click()
            deadline = time.time() + 300
            got = False
            while time.time() < deadline:
                app.processEvents()
                close_modals()
                if getattr(run_tab, "_solve_thread", None) is None and \
                   getattr(run_tab, "_solve_worker", None) is None:
                    got = True
                    break
                time.sleep(0.05)
            out["button_click_completed"] = got
            out["button_click_results_present"] = rcaide_io.rcaide_results is not None
            out["button_click_seconds"] = round(time.time() - t0, 1)
        except Exception:
            out["button_click_traceback"] = traceback.format_exc()
    return out

def do_performance_probe(app, tabs):
    from PyQt6.QtWidgets import QComboBox
    out = {}
    names = [tabs.tabText(i) for i in range(tabs.count())]
    if "Performance" not in names:
        return {"skipped": "no Performance tab"}
    tab = tabs.widget(names.index("Performance"))
    tabs.setCurrentIndex(names.index("Performance"))
    pump_guard(app, 0.4)
    combos = tab.findChildren(QComboBox)
    analysis_combo = getattr(tab, "analysis_combo", None)
    if analysis_combo is None:
        for c in combos:
            items = [c.itemText(i) for i in range(c.count())]
            if any("Take-Off Field Length" in t for t in items):
                analysis_combo = c
                break
    if analysis_combo is None:
        out["combo_items"] = [[c.itemText(i) for i in range(c.count())] for c in combos[:3]]
        return out
    out["items"] = [analysis_combo.itemText(i) for i in range(analysis_combo.count())]
    idx = None
    for i in range(analysis_combo.count()):
        if "Take-Off Field Length" in analysis_combo.itemText(i):
            idx = i
            break
    if idx is None:
        return out
    analysis_combo.setCurrentIndex(idx)
    out["selected"] = analysis_combo.currentText()
    pump_guard(app, 0.8)
    btn = find_button(tab, "Run Analysis")
    out["run_button_found"] = btn is not None
    if btn is None:
        return out
    btn.click()
    deadline = time.time() + 240
    done = False
    while time.time() < deadline:
        app.processEvents()
        close_modals()
        if getattr(tab, "_analysis_thread", None) is None and \
           getattr(tab, "_analysis_worker", None) is None:
            done = True
            break
        time.sleep(0.05)
    out["completed"] = done
    out["seconds"] = round(time.time() - t0 if False else 0, 1)
    # capture any textual results that landed on the tab
    try:
        from PyQt6.QtWidgets import QLabel
        texts = [l.text().strip() for l in tab.findChildren(QLabel) if l.text().strip()]
        out["label_texts_sample"] = texts[:40]
    except Exception:
        pass
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["capture", "simulate"])
    ap.add_argument("--load", default=None)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--direct", action="store_true", help="bypass Home dropdown, call load_file")
    ap.add_argument("--real", action="store_true", help="do not force offscreen platform")
    args = ap.parse_args()

    os.makedirs(OUT_IMG, exist_ok=True)
    os.makedirs(OUT_JSON, exist_ok=True)
    if not args.real:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")
    sys.path.insert(0, SP)

    report = {"timestamp": datetime.now().isoformat(), "mode": args.mode,
              "env": env_report()}
    log("== env ==")
    log(json.dumps(report["env"], ensure_ascii=False, indent=1))
    report["gl"] = gl_report()
    log("[GL] " + json.dumps(report["gl"], ensure_ascii=False, default=str)[:2000])

    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from PyQt6.QtGui import QFontDatabase
    report["font_families"] = len(QFontDatabase.families())
    log("[FONT] families=%d" % report["font_families"])

    import main as gui_main
    log("gui main module: %s" % gui_main.__file__)
    t0 = time.time()
    win = gui_main.App()
    report["window_build_seconds"] = round(time.time() - t0, 1)
    win.resize(1600, 1000)
    win.show()
    pump(app, 0.5)
    report["window_title"] = win.windowTitle()
    tabs = win.tabs
    report["tab_count"] = tabs.count()
    report["tab_names"] = [tabs.tabText(i) for i in range(tabs.count())]
    log("window=%r tabs=%d %s" % (win.windowTitle(), tabs.count(), report["tab_names"]))
    pump(app, 5.0)
    report["captures_startup"] = capture_all(app, tabs, args.tag or "tab")

    if args.load:
        ac = os.path.join(SP, "app_data", "aircraft", args.load + ".json")
        report["aircraft_path"] = ac
        report["aircraft_size"] = os.path.getsize(ac) if os.path.exists(ac) else None
        if not args.direct:
            report["home_dropdown_load"] = home_dropdown_load(app, tabs, win, args.load)
            log("[LOAD-VIA-DROPDOWN] " + json.dumps(report["home_dropdown_load"],
                                                    ensure_ascii=False, default=str)[:1500])
        if args.direct or not report.get("home_dropdown_load", {}).get("load_detected"):
            t0 = time.time()
            try:
                win.load_file(ac)
                report["load_ok"] = True
                report["load_seconds"] = round(time.time() - t0, 1)
                pump_guard(app, 1.5)
                log("[LOAD-DIRECT] ok %.1fs" % report["load_seconds"])
            except Exception:
                report["load_ok"] = False
                report["load_traceback"] = traceback.format_exc()
                log("[ERROR] load failed:\n" + report["load_traceback"])
        else:
            report["load_ok"] = True
            report["load_seconds"] = report["home_dropdown_load"].get("seconds")
        report["state_after_load"] = state_snapshot()
        log("[STATE] " + json.dumps(report["state_after_load"], ensure_ascii=False, default=str)[:3000])
        prefix = args.tag or "loaded"
        report["captures_loaded"] = capture_all(app, tabs, prefix)

        probe = {}
        try:
            an = tabs.widget(4)
            b = find_button(an, "Save Analyses")
            probe["button_found"] = b is not None
            if b is not None:
                try:
                    b.click()
                    probe["click_ok"] = True
                except Exception:
                    probe["click_ok"] = False
                    probe["click_traceback"] = traceback.format_exc()
                pump_guard(app, 0.6)
                import rcaide_io
                inner = {}
                for k, cont in rcaide_io.rcaide_analyses.items():
                    try:
                        inner[k] = [getattr(a, "tag", type(a).__name__) for a in cont]
                    except Exception:
                        inner[k] = str(type(cont))
                probe["analyses_after"] = inner
        except Exception:
            probe["error"] = traceback.format_exc()
        report["probe_save_analyses"] = probe
        log("[PROBE] save_analyses=" + json.dumps(probe, ensure_ascii=False, default=str)[:2000])

        if args.mode == "simulate":
            report["simulate"] = do_simulate(win, app, tabs)
            log("[SIM] " + json.dumps(report["simulate"], ensure_ascii=False, default=str)[:4000])
            report["captures_after_run"] = capture_all(app, tabs, "afterrun")
            try:
                report["performance_probe"] = do_performance_probe(app, tabs)
            except Exception:
                report["performance_probe"] = {"error": traceback.format_exc()}
            log("[PERF] " + json.dumps(report.get("performance_probe", {}),
                                       ensure_ascii=False, default=str)[:2000])

    report["app_alive_at_end"] = True
    outp = os.path.join(OUT_JSON, "gui_%s_report.json" % (args.tag or args.mode))
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    log("[DONE] %s" % outp)
    flush_log()
    try:
        win.shutdown_vtk()
    except Exception:
        pass
    app.quit()
    print("SMOKE-OK")

if __name__ == "__main__":
    main()

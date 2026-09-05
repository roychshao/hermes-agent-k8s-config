import sys

filepath = "/opt/hermes/tools/kanban_tools.py"
try:
    with open(filepath, "r") as f:
        code = f.read()

    # 1. Allow kanban_list in _require_orchestrator_tool
    target_req = """def _require_orchestrator_tool(tool_name: str) -> Optional[str]:
    \"\"\"Belt-and-suspenders runtime guard for orchestrator-only handlers.

    The check_fn (`_check_kanban_orchestrator_mode`) keeps these tools
    out of the worker schema entirely, but in case a stale registration
    or test harness routes a worker to one of them anyway, return a
    structured tool_error so the model gets a clear refusal instead of
    silently mutating board state from a worker context.
    \"\"\"
    if os.environ.get("HERMES_KANBAN_TASK"):"""

    replacement_req = """def _require_orchestrator_tool(tool_name: str) -> Optional[str]:
    \"\"\"Belt-and-suspenders runtime guard for orchestrator-only handlers.

    The check_fn (`_check_kanban_orchestrator_mode`) keeps these tools
    out of the worker schema entirely, but in case a stale registration
    or test harness routes a worker to one of them anyway, return a
    structured tool_error so the model gets a clear refusal instead of
    silently mutating board state from a worker context.
    \"\"\"
    if tool_name == "kanban_list":
        return None
    if os.environ.get("HERMES_KANBAN_TASK"):"""

    if target_req in code:
        code = code.replace(target_req, replacement_req)
        print("Patched _require_orchestrator_tool successfully!")

    # 2. Register kanban_list with _check_kanban_mode
    target_reg = """registry.register(
    name="kanban_list",
    toolset="kanban",
    schema=KANBAN_LIST_SCHEMA,
    handler=_handle_list,
    check_fn=_check_kanban_orchestrator_mode,
    emoji="📋",
)"""

    replacement_reg = """registry.register(
    name="kanban_list",
    toolset="kanban",
    schema=KANBAN_LIST_SCHEMA,
    handler=_handle_list,
    check_fn=_check_kanban_mode,
    emoji="📋",
)"""

    if target_reg in code:
        code = code.replace(target_reg, replacement_reg)
        print("Patched kanban_list registration successfully!")

    # 3. Add disambiguation warning to KANBAN_LINK_SCHEMA description
    target_link = """KANBAN_LINK_SCHEMA = {
    "name": "kanban_link",
    "description": (
        "Add a parent→child dependency edge after both tasks already "
        "exist. The child won't promote to 'ready' until all parents "
        "are 'done'. Cycles and self-links are rejected."
    ),"""

    replacement_link = """KANBAN_LINK_SCHEMA = {
    "name": "kanban_link",
    "description": (
        "Add a parent→child dependency edge between two tasks (child waits for parent). "
        "WARNING: DO NOT use kanban_link to list or view tasks (use kanban_list instead). "
        "Cycles and self-links are rejected."
    ),"""

    if target_link in code:
        code = code.replace(target_link, replacement_link)
        print("Patched KANBAN_LINK_SCHEMA description successfully!")

    # 4. Support workspace as alias for workspace_kind in _handle_create
    target_ws = '    workspace_kind = args.get("workspace_kind")'
    replacement_ws = '    workspace_kind = args.get("workspace_kind") or args.get("workspace")'
    if target_ws in code:
        code = code.replace(target_ws, replacement_ws, 1)
        print("Patched workspace_kind alias in _handle_create successfully!")

    with open(filepath, "w") as f:
        f.write(code)
    print("kanban_tools.py patch completed successfully!")

except Exception as e:
    print(f"Failed to patch kanban_tools.py: {e}")
    sys.exit(1)

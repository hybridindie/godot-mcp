# Godot Testing & GUT

## GUT setup

### Install GUT

```bash
gh api repos/bitwes/Gut/zipball/v9.7.1 > /tmp/gut.zip
unzip /tmp/gut.zip -d /tmp/gut-src
cp -R /tmp/gut-src/bitwes-Gut-*/addons/gut <project>/addons/
```

Add to `project.godot`:
```ini
[editor_plugins]
enabled=PackedStringArray("res://addons/godot_mcp/plugin.cfg", "res://addons/gut/plugin.cfg")
```

Create `.gutconfig.json`:
```json
{
  "dirs": ["res://tests/unit"],
  "should_exit": true,
  "log_level": 1
}
```

### Run tests

```bash
# Via the MCP tool (agents use this):
godot_testing_run_tests(test_dir="res://tests/unit")

# Directly:
godot --headless --path <project> -s addons/gut/gut_cmdln.gd -gexit

# Subset:
godot --headless --path <project> -s addons/gut/gut_cmdln.gd -gexit \
  -gselect=test_player
```

---

## Test patterns

### Basic test structure

```gdscript
extends GutTest

var _player: CharacterBody2D

func before_each() -> void:
    _player = CharacterBody2D.new()
    _player.set_script(load("res://scripts/player.gd"))
    add_child(_player)

func after_each() -> void:
    _player.free()

func test_player_starts_with_full_health() -> void:
    assert_eq(_player.health, 100.0, "Starts at 100 HP")
```

### Signal assertions

```gdscript
func test_death_emits_died() -> void:
    watch_signals(_player)
    _player.take_damage(100.0)
    assert_signal_emitted(_player, "died")

func test_no_signal_above_zero() -> void:
    watch_signals(_enemy)
    _enemy.take_damage(10.0)
    assert_signal_not_emitted(_enemy, "enemy_died")
```

### Group membership

```gdscript
func test_enemy_in_group() -> void:
    assert_true(_enemy.is_in_group("enemies"), "Should be in enemies group")
```

### State machine tests

```gdscript
func test_start_transitions_to_playing() -> void:
    _gm.start_game()
    assert_eq(_gm.state, _gm.State.PLAYING)
    assert_false(get_tree().paused, "Playing should not pause")
```

### Regression test for signal removal

```gdscript
func test_old_signal_removed() -> void:
    var sigs := _gm.get_signal_list()
    for sig in sigs:
        assert_ne(sig["name"], "game_over",
            "game_over signal should be removed; use state_changed")
```

---

## GUT gotchas

### Don't await `ready` on simple nodes

```gdscript
# ❌ Hangs — _ready fires synchronously on add_child:
func before_each() -> void:
    _player = CharacterBody2D.new()
    _player.set_script(load("res://scripts/player.gd"))
    add_child(_player)
    await wait_for_signal(_player.ready, 1.0)  # HANGS

# ✅ _ready already fired:
func before_each() -> void:
    _player = CharacterBody2D.new()
    _player.set_script(load("res://scripts/player.gd"))
    add_child(_player)
    # No await needed
```

### Don't instantiate heavy scenes in before_each

```gdscript
# ❌ Hangs — main.tscn generates 800+ tiles and 40 obstacles:
func before_each() -> void:
    _main = load("res://scenes/main.tscn").instantiate()
    add_child(_main)

# ✅ Instantiate just the node + script:
func before_each() -> void:
    _player = CharacterBody2D.new()
    _player.set_script(load("res://scripts/player.gd"))
    add_child(_player)
```

### assert_contains doesn't exist in GUT 9.7

```gdscript
# ❌ Parse error:
assert_contains(label.text, "500", "score shown")

# ✅ Use assert_string_contains:
assert_string_contains(label.text, "500", "score shown")
```

### Autoload state leaks between tests

```gdscript
# ❌ GameManager keeps state from the previous test:
func before_each() -> void:
    _gm = get_node("/root/GameManager")
    # _gm.state might be GAME_OVER from the last test

# ✅ Reset in before_each:
func before_each() -> void:
    _gm = get_node("/root/GameManager")
    _gm._change_state(_gm.State.MENU)
```

### Godot 4.7 type inference in tests

```gdscript
# ❌ Parse error:
var main := load("res://scenes/main.tscn").instantiate()
var initial_max := _player.max_health

# ✅ Explicit types:
var main: Node = load("res://scenes/main.tscn").instantiate()
var initial_max: float = _player.max_health
```

---

## MCP run_tests tool

The `godot_testing_run_tests` tool (in the `testing` toolset) runs GUT
headlessly and returns structured results:

```
godot_testing_run_tests(test_dir="res://tests/unit", timeout_seconds=120)
→ RunTestsResult {
    ran: true,
    framework: "gut",
    framework_absent: false,  # true when GUT not installed (not an error)
    passed: 57,
    failed: 0,
    total: 57,
    failures: [...],
    raw_summary: "..."
  }
```

**GUT dependency is optional:** if GUT isn't installed
(`addons/gut/gut_cmdln.gd` missing), the tool returns
`framework_absent=true` (a normal outcome, not an error).

**Parser note:** GUT 9.7+ omits the "Failing Tests" line when all tests
pass. The godot-mcp parser handles this (fixed in `gut_parse.py`).
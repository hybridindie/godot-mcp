extends CanvasLayer
## Upgrade menu for Vampire Survivors demo.
## Must process during pause so buttons work while the tree is frozen.

const UPGRADES := [
	{"type": "speed", "name": "Speed Up", "desc": "Move 10% faster"},
	{"type": "max_health", "name": "Max Health", "desc": "+20 HP"},
	{"type": "damage", "name": "Damage Up", "desc": "+5 damage"},
	{"type": "attack_speed", "name": "Attack Speed", "desc": "Attack 10% faster"},
	{"type": "projectile_count", "name": "Multi-Shot", "desc": "+1 projectile"},
	{"type": "area_size", "name": "Area Up", "desc": "+15 area radius"},
	{"type": "magnet", "name": "Magnet", "desc": "+30 pickup range"},
	{"type": "regen", "name": "Regen", "desc": "Heal 1 HP/sec"},
]

@onready var options_container: VBoxContainer = $Panel/VBoxContainer/OptionsContainer

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS

func generate_options() -> void:
	# Clear existing
	for child in options_container.get_children():
		child.queue_free()
	
	# Pick 3 random upgrades
	var available := UPGRADES.duplicate()
	available.shuffle()
	var options := available.slice(0, 3)
	
	for upgrade in options:
		var button := Button.new()
		button.process_mode = Node.PROCESS_MODE_ALWAYS
		button.text = "%s\n%s" % [upgrade["name"], upgrade["desc"]]
		button.custom_minimum_size = Vector2(0, 60)
		button.pressed.connect(_on_upgrade_selected.bind(upgrade["type"]))
		options_container.add_child(button)

func _on_upgrade_selected(upgrade_type: String) -> void:
	GameManager.apply_upgrade(upgrade_type)

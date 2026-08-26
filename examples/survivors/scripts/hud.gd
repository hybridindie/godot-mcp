extends CanvasLayer

@onready var health_bar: ProgressBar = $HealthBar
@onready var xp_bar: ProgressBar = $XPBar
@onready var score_label: Label = $ScoreLabel
@onready var wave_label: Label = $WaveLabel

func _ready() -> void:
	var player: Node2D = get_tree().get_first_node_in_group("player")
	if player:
		player.health_changed.connect(_on_health_changed)
		player.xp_changed.connect(_on_xp_changed)
	var gm := get_node_or_null("/root/GameManager")
	if gm:
		gm.score_changed.connect(_on_score_changed)
		gm.wave_changed.connect(_on_wave_changed)

func _on_health_changed(hp: float, max_hp: float) -> void:
	health_bar.value = (hp / max_hp) * 100.0

func _on_xp_changed(xp: int, level: int, to_next: int) -> void:
	xp_bar.value = (float(xp) / float(to_next)) * 100.0

func _on_score_changed(s: int) -> void:
	score_label.text = "Score: %d" % s

func _on_wave_changed(w: int) -> void:
	wave_label.text = "Wave: %d" % w
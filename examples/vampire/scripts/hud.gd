extends CanvasLayer
## HUD for Vampire Survivors demo.

@onready var health_bar: ProgressBar = $HealthBar
@onready var xp_bar: ProgressBar = $XPBar
@onready var score_label: Label = $ScoreLabel
@onready var wave_label: Label = $WaveLabel
@onready var timer_label: Label = $TimerLabel

func _ready() -> void:
	update_bars(100, 100, 0, 100)
	update_score(0)
	update_wave(1)
	update_time(0)

func update_bars(health: int, max_health: int, xp: int, xp_to_next: int) -> void:
	health_bar.max_value = max_health
	health_bar.value = health
	xp_bar.max_value = xp_to_next
	xp_bar.value = xp

func update_score(score: int) -> void:
	score_label.text = "Kills: %d" % score

func update_wave(wave: int) -> void:
	wave_label.text = "Wave: %d" % wave

func update_time(time: float) -> void:
	var minutes := int(time) / 60
	var seconds := int(time) % 60
	timer_label.text = "%02d:%02d" % [minutes, seconds]

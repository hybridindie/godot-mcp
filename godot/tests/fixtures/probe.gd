@tool
extends Node2D
## Test fixture: a node with exported script variables, used to verify
## MCPSceneInspect.node_properties() picks up exported/script properties.

@export var speed: float = 200.0
@export var health: int = 100

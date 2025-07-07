'''
Purpose: Core data model for all cards.
Responsibilities:
	Stores all metadata:
	•	Cost, Thresholds (Air/Earth/Fire/Water), Stats (Attack, Defense, Life)
	•	Type (Site, Minion, Avatar, Artifact, Aura, Magic)
	•	Subtypes (Tower, Beast, etc)
	•	States (Airborne, Submerge, etc.)
	Implements:
	•	move() — respects movement rules and constraints
	•	attack() — handles strike resolution and triggered responses
	•	resolve_ability() — for passive, activated, and triggered effects
	•	Stores internal state: isTapped, hasSummoningSickness, isCarrying, etc.
	•	Card objects are passed into Rule_Engine for parsing Rule Text into actual abilities.
'''


class CardInfo:
	def __init__(self, image_url, sorcery_data):
		self.name = sorcery_data.get("name")
		self.elements = sorcery_data.get("elements")  # can be multiple
		self.subtypes = sorcery_data.get("subTypes")  # can be multiple
		guardian = sorcery_data.get("guardian")  # the metadata:
		self.rareity = guardian.get("rarity")
		self.type = guardian.get("type")
		self.rules_text = guardian.get("rulesText")
		self.cost = guardian.get("cost")
		self.attack = guardian.get("attack")
		self.defence = guardian.get("defence")
		self.life = guardian.get("life")
		self.thresholds = guardian.get("thresholds")
		self.image_url = image_url
  
		self.artifacts = []
		self.movement = 1
		self.range = 1
  
		self.isTapped = False
		self.hasSummoningSickness = False
		self.isCarrying = False
		self.isDisabled = False  # (Can’t do anything except be forcibly moved or tapped)
		self.isImmobile = False  # (Can’t move, move and attack, intercept, or defend)
  
		self.isAirborne = False
		self.isSubmergeable = False
		self.isBurrowable = False
		self.isStealthy = False
		self.isLeathal = False  # (Kills what it strikes, damage=999)
		self.isWaterbound = False  # (disabled when on land)
		self.isLandbound = False  # (disabled when on water)
		self.isVoidwalker = False  # (can walk on void)
		self.isSpellcaster = False  #
		self.isRanged = False  #
	
		self.set_differences = self._check_metadata_differences(sorcery_data.get("sets"), guardian)

	def _check_metadata_differences(self, sets, guardian):
		"""Compare set metadata with guardian info and flag if they differ."""
		differences = []
		for s in sets:
			meta = s.get("metadata", {})
			if not self._dicts_equal(meta, guardian):
				differences.append(s["name"])
		return differences

	@staticmethod
	def _dicts_equal(d1, d2):
		"""Compare two dictionaries for equality, ignoring trivial newline formatting."""
		def normalize(d):
			if not d: 
				return {}
			return {
				k: v.strip().replace("\r", "").replace("\n", " ")
				if isinstance(v, str) else v
				for k, v in d.items()
			}
		return normalize(d1) == normalize(d2)

	def has_single_version(self):
		return len(self.set_differences) == 0

	def summary(self):
		version = "Single" if self.has_single_version() else f"Variants in: {', '.join(self.set_differences)}"
		return f"{self.name} [{self.type}] - {version}"
	
 
'''
	Curiosa Card Data Example:
		"identifier": "avatar_of_air",
		"name": "Avatar of Air",
		"quantity": 1,
		"src": "https://d27a44hjr9gen3.cloudfront.net/alp/avatar_of_air_d_s.png",
		"metadata": {
			"type": "Avatar",
			"waterThreshold": 0,
			"earthThreshold": 0,
			"airThreshold": 0,
			"fireThreshold": 0
			}
	Sorcery Card Data Example:
		{
			"name": "Blood Ravens",
			"guardian": {
				"rarity": "Ordinary",
				"type": "Minion",
				"rulesText": "Airborne\r\n \r\nDamage dealt by Blood Ravens' strikes heals you.",
				"cost": 1,
				"attack": 1,
				"defence": 1,
				"life": null,
				"thresholds": {
					"air": 1,
					"earth": 0,
					"fire": 0,
					"water": 0
					}
				},
			"elements": "Air",
			"subTypes": "Beast",
			"sets": [...]
'''

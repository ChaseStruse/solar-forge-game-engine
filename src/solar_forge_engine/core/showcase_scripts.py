"""Readable scene-script examples copied into the native showcase editor.

These are source strings, never imported/executed by the editor. Their only runtime
contract is the documented scene Python API; Play uses the restricted worker.
"""

EMBER_SCRIPT = """# EMBER RUN — reactive pickups, orbiting sparks and a timed finish.
# Try changing these values, Apply script, then start Play again.
BASE_SPEED = 220
BOOST_SPEED = 330
BOOST_SECONDS = 1.4
CORE_BOB_HEIGHT = 4
SPARK_RADIUS = 78


def on_start(game):
    # Save authored positions once: offsets never accumulate between frames.
    game.data["cores"] = [
        (obj["id"], obj["x"], obj["y"])
        for obj in game.objects.values() if obj["role"] == "coin"
    ]
    game.data["sparks"] = [
        obj["id"] for obj in game.objects.values()
        if obj["name"].startswith("Reactor spark")
    ]
    game.data["last_count"] = 0
    game.data["boost_until"] = 0
    game.data["boosting"] = False
    game.data["finished"] = False
    game.data["last_message"] = ""
    game.set_speed(BASE_SPEED)
    game.say("EMBER RUN | Recover 12 cores. Pickups boost your engines! WASD / arrows")
    print("Ember Run: edit the constants above to tune your own forge run.")


def on_update(game, dt):
    t = game.time
    count = game.collected
    data = game.data

    # Each core has its own phase, creating a travelling wave across the forge.
    for index, (core_id, x, y) in enumerate(data["cores"]):
        game.set_position(core_id, x, y + math.sin(t * 3 + index * 0.7) * CORE_BOB_HEIGHT)

    # Six sparks orbit the reactor. After victory they celebrate around the pilot.
    center_x, center_y = 512, 288
    radius_x, radius_y = SPARK_RADIUS, 114
    if data["finished"]:
        center_x = game.player["x"] + game.player["width"] / 2
        center_y = game.player["y"] + game.player["height"] / 2
        radius_x = radius_y = 38
    for index, spark_id in enumerate(data["sparks"]):
        angle = t * 1.8 + index * math.tau / max(1, len(data["sparks"]))
        game.set_position(spark_id,
                          center_x + math.cos(angle) * radius_x - 6,
                          center_y + math.sin(angle) * radius_y - 6)

    # React to changes in the collection count, not to every frame of an overlap.
    if count > data["last_count"]:
        data["last_count"] = count
        data["boost_until"] = t + BOOST_SECONDS
        print("Core recovered:", count, "/", game.total_coins)

    if game.total_coins and count == game.total_coins and not data["finished"]:
        data["finished"] = True
        medal = "SOLAR ACE" if t < 45 else "FORGE RUNNER" if t < 75 else "CORE KEEPER"
        data["finish_message"] = f"{medal} | All cores secured in {t:.1f}s! Restart to race again."
        print(data["finish_message"])

    boosting = t < data["boost_until"] and not data["finished"]
    if boosting != data["boosting"]:
        game.set_speed(BOOST_SPEED if boosting else BASE_SPEED)
        data["boosting"] = boosting

    # Send HUD commands only when the displayed text changes.
    if data["finished"]:
        message = data["finish_message"]
    elif boosting:
        message = f"OVERDRIVE! | {count}/{game.total_coins} cores | Engines boosted"
    elif t < 4 and count == 0:
        message = "EMBER RUN | Recover 12 cores. Pickups boost your engines! WASD / arrows"
    else:
        sector = "REACTOR ONLINE" if count >= 8 else "FORGE WARMING" if count >= 4 else "POWER LOW"
        message = f"{sector} | {count}/{game.total_coins} cores | {int(t)}s | Keep moving!"
    if message != data["last_message"]:
        game.say(message)
        data["last_message"] = message
"""

BAY_SCRIPT = """# COURIER BAY — a small lesson in circular motion and state changes.
# Increase ORBIT_SPEED for a harder chase; set it to 0 for stationary targets.
ORBIT_SPEED = 0.45
ORBIT_RADIUS = 180
BOB_HEIGHT = 8


def on_start(game):
    game.data["cores"] = [
        obj["id"] for obj in game.objects.values() if obj["role"] == "coin"
    ]
    game.data["last_count"] = -1
    game.data["finished"] = False
    game.set_speed(280)
    game.say("ORBIT LAB | Chase the four satellites. WASD / arrows")
    print("Orbit Lab: try ORBIT_SPEED = 0, or change ORBIT_RADIUS in the script editor.")


def on_update(game, dt):
    t = game.time
    cores = game.data["cores"]
    # Circular x/y motion uses cosine and sine of the same angle.
    # All four objects share one rule, spaced equally around the ring.
    for index, core_id in enumerate(cores):
        angle = t * ORBIT_SPEED + index * math.tau / max(1, len(cores))
        game.set_position(core_id,
                          512 + math.cos(angle) * ORBIT_RADIUS - 16,
                          288 + math.sin(angle) * ORBIT_RADIUS - 16)
    game.set_position("bay-reactor", 480, 192 + math.sin(t * 2) * BOB_HEIGHT)

    if game.collected != game.data["last_count"]:
        game.data["last_count"] = game.collected
        if game.total_coins and game.collected == game.total_coins:
            game.data["finished"] = True
            game.say(f"ORBIT COMPLETE | Four satellites caught in {t:.1f}s! Restart to retry.")
            print("Orbit complete! Change the constants and build your own challenge.")
        elif game.collected:
            game.say(f"SATELLITE CAPTURED | {game.collected}/{game.total_coins} | Keep chasing!")
"""

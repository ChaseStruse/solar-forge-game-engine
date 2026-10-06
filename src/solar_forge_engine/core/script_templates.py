"""Small Python behaviors shared by manual authoring and offline proposal fixtures."""

TEMPLATES = {
    "Keyboard movement": """def update(ctx, dt):
    speed = 240
    ctx.move(ctx.input.horizontal * speed * dt,
             ctx.input.vertical * speed * dt)


def on_collect(ctx, other_id):
    ctx.add_score(10)
""",
    "Patrol": """def start(ctx):
    ctx.state["origin"] = ctx.x
    ctx.state["direction"] = 1


def update(ctx, dt):
    origin = ctx.state["origin"]
    direction = ctx.state["direction"]
    if ctx.x >= origin + 120:
        direction = -1
    elif ctx.x <= origin:
        direction = 1
    ctx.state["direction"] = direction
    ctx.move(direction * 80 * dt, 0)


def on_collision(ctx, other_id):
    ctx.state["direction"] *= -1
""",
    "Spin and pulse": """import math


def update(ctx, dt):
    ctx.set_rotation(ctx.elapsed * 90)
    ctx.set_color("#f3cb77" if math.sin(ctx.elapsed * 3) > 0 else "#77e6b6")
""",
}

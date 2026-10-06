import math


def start(ctx):
    ctx.state["origin"] = (ctx.x, ctx.y)


def update(ctx, dt):
    x, y = ctx.state["origin"]
    ctx.set_position(x + math.sin(ctx.elapsed * 0.8) * 12, y + math.sin(ctx.elapsed * 1.6) * 5)
    ctx.set_rotation(math.sin(ctx.elapsed * 0.8) * 8)

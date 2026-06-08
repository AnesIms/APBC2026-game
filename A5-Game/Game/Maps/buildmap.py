width = 29
height = 29

border_width = 3
cross_width = 5

center = width // 2
half_cross = cross_width // 2

lines = []

for y in range(height):
    row = ""

    for x in range(width):
        in_outer_ring = (
            x < border_width
            or x >= width - border_width
            or y < border_width
            or y >= height - border_width
        )

        in_vertical_cross = abs(x - center) <= half_cross
        in_horizontal_cross = abs(y - center) <= half_cross

        if in_outer_ring or in_vertical_cross or in_horizontal_cross:
            row += "."
        else:
            row += "#"

    lines.append(row)

with open("cross_map.dat", "w") as f:
    f.write("\n".join(lines))
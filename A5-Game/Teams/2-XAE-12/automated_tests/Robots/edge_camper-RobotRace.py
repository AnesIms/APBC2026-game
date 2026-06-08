from Game.game_utils import Direction as D
from Game.game_utils import Map, TileStatus
from Game.player_base import Player
from collections import deque


class EdgeCamperBot(Player):
    """
    Conservative test bot:
    - First moves to a known map edge.
    - Then camps there and collects +1 gold per round.
    - Only moves toward gold if the gold is within 5 known path steps.
    """

    GOLD_PICKUP_DISTANCE = 5

    def reset(self, player_id, max_players, width, height):
        self.player_name = "EdgeCamper"
        self.ourMap = Map(width, height)
        self.player_id = player_id
        self.max_players = max_players
        self.edge_target = None
        self.reached_edge = False

    def round_begin(self, r):
        pass

    def set_mines(self, status):
        return []

    # --------------------------------------------------------
    # Basic helpers
    # --------------------------------------------------------

    def in_bounds(self, x, y):
        return 0 <= x < self.ourMap.width and 0 <= y < self.ourMap.height

    def is_known_free(self, x, y):
        if not self.in_bounds(x, y):
            return False
        return self.ourMap[x, y].status == TileStatus.Empty

    def direction_from_to(self, start_x, start_y, target_x, target_y):
        dx = target_x - start_x
        dy = target_y - start_y

        for direction in D:
            dir_x, dir_y = direction.as_xy()
            if (dir_x, dir_y) == (dx, dy):
                return direction

        return None

    def is_edge_position(self, pos):
        x, y = pos
        return (
            x == 0
            or y == 0
            or x == self.ourMap.width - 1
            or y == self.ourMap.height - 1
        )

    # --------------------------------------------------------
    # Map update
    # --------------------------------------------------------

    def update_map(self, status):
        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                if status.map[x, y].status != TileStatus.Unknown:
                    self.ourMap[x, y].status = status.map[x, y].status

    # --------------------------------------------------------
    # Pathfinding
    # --------------------------------------------------------

    def shortest_path(self, start, goal):
        queue = deque([start])
        came_from = {start: None}

        while queue:
            current = queue.popleft()

            if current == goal:
                break

            for direction in D:
                dx, dy = direction.as_xy()
                next_pos = (current[0] + dx, current[1] + dy)

                if next_pos in came_from:
                    continue

                if not self.in_bounds(*next_pos):
                    continue

                if next_pos == goal:
                    if self.ourMap[next_pos[0], next_pos[1]].status == TileStatus.Wall:
                        continue
                elif not self.is_known_free(*next_pos):
                    continue

                came_from[next_pos] = current
                queue.append(next_pos)

        if goal not in came_from:
            return None

        path = []
        current = goal

        while current is not None:
            path.append(current)
            current = came_from[current]

        path.reverse()
        return path

    def first_move_from_path(self, path):
        if path is None or len(path) < 2:
            return []

        start_x, start_y = path[0]
        next_x, next_y = path[1]

        direction = self.direction_from_to(start_x, start_y, next_x, next_y)

        if direction is None:
            return []

        return [direction]

    # --------------------------------------------------------
    # Edge target selection
    # --------------------------------------------------------

    def find_best_known_edge_path(self, current_pos):
        best_path = None
        best_length = float("inf")

        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                candidate = (x, y)

                if not self.is_edge_position(candidate):
                    continue

                if not self.is_known_free(x, y):
                    continue

                path = self.shortest_path(current_pos, candidate)

                if path is None or len(path) < 2:
                    continue

                path_length = len(path) - 1

                if path_length < best_length:
                    best_length = path_length
                    best_path = path

        return best_path

    # --------------------------------------------------------
    # Main move
    # --------------------------------------------------------

    def move(self, status):
        self.update_map(status)

        if status.health < 30:
            return []

        current_pos = (status.x, status.y)

        if self.is_edge_position(current_pos):
            self.reached_edge = True

        if not status.goldPots:
            return []

        gold_pos = next(iter(status.goldPots))

        # If gold is close by, collect it.
        path_to_gold = self.shortest_path(current_pos, gold_pos)

        if path_to_gold is not None:
            distance_to_gold = len(path_to_gold) - 1

            if distance_to_gold <= self.GOLD_PICKUP_DISTANCE:
                return self.first_move_from_path(path_to_gold)

        # If we already reached the edge, camp.
        if self.reached_edge:
            return []

        # Otherwise move toward the nearest known edge field.
        path_to_edge = self.find_best_known_edge_path(current_pos)

        if path_to_edge is not None:
            return self.first_move_from_path(path_to_edge)

        # If no known edge path exists yet, stay still.
        return []


players = [EdgeCamperBot()]
from game_utils import Direction as D 
from game_utils import Map, TileStatus 
from player_base import Player
from collections import deque
# Import movement directions, map handling, tile information (is the tile a wall, unknown ...), and the base Player class

class StrategyOneBot(Player):
    # - remember discovered parts of the map
    # - use BFS to find known shortest paths to the gold
    # - explore unknown areas if no useful path to the gold is known
    # - buy multiple moves per round when rushing to gold is worth the cost
    
    def reset(self, player_id, max_players, width, height):
        self.player_name = "XAE-12 S1"
        self.ourMap = Map(width, height)
        # Called once at the beginning of a game.
        # ourMap is our remembered map.
        # It starts mostly unknown, but during the game we continuously update it
        # with all visible fields from the current status.
    
    def round_begin(self, r):
        pass
    # This method is called at the beginning of each round.
    # We currently do not use it, but it could later be useful for
    # round-based strategies, such as detecting gold relocation timing.

    def in_bounds(self, x, y):
    # Return True if the coordinate is inside the map.
        return 0 <= x < self.ourMap.width and 0 <= y < self.ourMap.height

    def is_known_free(self, x, y):
    # Return True if the field is inside the map and known to be empty
        if not self.in_bounds(x, y):
            return False

        return self.ourMap[x, y].status == TileStatus.Empty

    def direction_from_to(self, start_x, start_y, target_x, target_y):
    # Convert two neighboring coordinates into the corresponding movement direction.
        dx = target_x - start_x
        dy = target_y - start_y

        for direction in D:
            dir_x, dir_y = direction.as_xy()
            if (dir_x, dir_y) == (dx, dy):
                return direction

        return None


    def shortest_path(self, start, goal):
    """
    Find the shortest known path with BFS.
    Intermediate fields must be known empty; the gold goal may be entered
    as long as it is not a known wall.
    """
        queue = deque([start])
        came_from = {start: None}

        while queue:
            current_x, current_y = queue.popleft()

            if (current_x, current_y) == goal:
                break

            for direction in D:
                dx, dy = direction.as_xy()
                next_x = current_x + dx
                next_y = current_y + dy
                next_pos = (next_x, next_y)

                if next_pos in came_from:
                    continue

                if next_pos == goal:
                    if not self.in_bounds(next_x, next_y):
                        continue
                    if self.ourMap[next_x, next_y].status == TileStatus.Wall:
                        continue
                else:
                    if not self.is_known_free(next_x, next_y):
                        continue

                came_from[next_pos] = (current_x, current_y)
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


    def find_frontiers(self):
    # Find known empty fields that border unknown areas and are useful for exploration.
        frontiers = []

        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                if self.ourMap[x, y].status != TileStatus.Empty:
                    continue

                for direction in D:
                    dx, dy = direction.as_xy()
                    neighbor_x = x + dx
                    neighbor_y = y + dy

                    if not self.in_bounds(neighbor_x, neighbor_y):
                        continue

                    if self.ourMap[neighbor_x, neighbor_y].status == TileStatus.Unknown:
                        frontiers.append((x, y))
                        break

        return frontiers

    
    def choose_best_frontier(self, position, gold_position):
        # Choose the reachable frontier that is close to us and still roughly points toward the gold.
        frontiers = self.find_frontiers()

        best_path = None
        best_score = float("inf")

        for frontier in frontiers:
            path = self.shortest_path(position, frontier)

            if path is None or len(path) < 2:
                continue

            distance_to_frontier = len(path) - 1
            distance_to_gold = max(
                abs(gold_position[0] - frontier[0]),
                abs(gold_position[1] - frontier[1])
            )


            # The score prefers nearby frontiers, but adds a smaller penalty for being far from the gold.
            # This makes exploration still move roughly toward the current gold instead of wandering randomly.
            score = distance_to_frontier + 0.5 * distance_to_gold

            if score < best_score:
                best_score = score
                best_path = path

        return best_path


    def move_cost(self, number_of_moves):
        return number_of_moves * (number_of_moves + 1) // 2


    def choose_burst_length(self, path_length, gold_value, current_gold):
        # Decide how many moves to buy without spending too much gold for the current pot.
        max_burst_moves = 5
        gold_spend_fraction = 0.25 # Spend max 25% of the current gold pot value
        minimum_gold_reserve = 20

        burst_length = 1

        for number_of_moves in range(1, min(path_length, max_burst_moves) + 1):
            cost = self.move_cost(number_of_moves)

            if cost > current_gold - minimum_gold_reserve:
                break

            if cost > gold_value * gold_spend_fraction:
                break

            burst_length = number_of_moves

        return burst_length


    def path_to_moves(self, path, max_moves):
        # Convert the next coordinates of a planned path into actual movement directions.

        moves = []

        for i in range(1, min(len(path), max_moves + 1)):
            start_x, start_y = path[i - 1]
            next_x, next_y = path[i]

            direction = self.direction_from_to(start_x, start_y, next_x, next_y)

            if direction is None:
                break

            moves.append(direction)

        return moves


    def is_gold_path_reasonable(self, position, gold_position, path):
        # Accept a known gold path only if it is not an excessive detour.

        path_length = len(path) - 1

        direct_distance = max(
            abs(gold_position[0] - position[0]),
            abs(gold_position[1] - position[1])
        )

        return path_length <= direct_distance * 2 + 5

    def move(self, status):
        # Update remembered map with all currently visible fields
        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                if status.map[x, y].status != TileStatus.Unknown:
                    self.ourMap[x, y].status = status.map[x, y].status
        # Update internal map with all currently visible fields.
        # Unknown fields are ignored, so previously discovered information is not overwritten.
        
        # If health is too low, do not move
        if status.health < 30:
            return []

        # Get current position and nearest known gold pot
        current_position = (status.x, status.y)
        gold_position = next(iter(status.goldPots))

        # Try to find a shortest path to the gold using our remembered map
        path_to_gold = self.shortest_path(current_position, gold_position)

        if (
            path_to_gold is not None
            and len(path_to_gold) > 1
            and self.is_gold_path_reasonable(current_position, gold_position, path_to_gold)
        ):
            path_length = len(path_to_gold) - 1
            gold_value = status.goldPots[gold_position]

        # Buy several moves if the path is good and the gold pot is worth the cost.
            burst_length = self.choose_burst_length(
                path_length,
                gold_value,
                status.gold
            )

            moves = self.path_to_moves(path_to_gold, burst_length)

            if moves:
                return moves

        # If no known path to the gold was found, explore a reachable frontier
        path_to_frontier = self.choose_best_frontier(current_position, gold_position)

        if path_to_frontier is not None and len(path_to_frontier) > 1:
            next_x, next_y = path_to_frontier[1]
            direction = self.direction_from_to(status.x, status.y, next_x, next_y)

            if direction is not None:
                return [direction]

        # If neither gold nor frontier is reachable, stay in place
        return []

players = [StrategyOneBot()]
# The simulator imports this list to load our bot.
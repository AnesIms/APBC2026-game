
from Game.game_utils import Direction as D 
from Game.game_utils import Map, TileStatus 
from Game.player_base import Player
# Import movement directions, map handling, tile information (is the tile a wall, unknown ...), and the base Player class

# Our simple baseline bot. remembers discovered walls and greedily moves one step toward the gold
class BaselineBot(Player):
    def reset(self, player_id, max_players, width, height):
        self.player_name = "XAE-12 Baseline"
        self.ourMap = Map(width, height)
        # Called once at the beginning of a game.
        # Store the bot name and create an internal map to remember discovered fields.

    def round_begin(self, r):
        pass
    # Currently not used, but could be useful for round-based strategies later.

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

        # Find possible neighboring fields that are not known walls
        possible_moves = []

        for direction in D:
            dx, dy = direction.as_xy()
            new_x = status.x + dx
            new_y = status.y + dy
            # Check all neighboring fields and collect moves that do not lead into known walls.
            
            if new_x < 0 or new_x >= self.ourMap.width:
                continue
            if new_y < 0 or new_y >= self.ourMap.height:
                continue
            # Skip moves that would leave the board.

            tile = self.ourMap[new_x, new_y]

            if tile.status != TileStatus.Wall:
                possible_moves.append((direction, (new_x, new_y)))
            # Allow every move that does not lead into a known wall.
            # Unknown fields are allowed so the bot can still explore.

        if not possible_moves:
            return []
        # If no safe move is available, stay in place.

        # Move toward the nearest known gold pot
        gold_position = next(iter(status.goldPots))

        # the distance to the gold is calculated for every possible move.
        # takes the move with the smallest distance
        best_direction, best_position = min(
            possible_moves,
            key=lambda move: max(
                abs(gold_position[0] - move[1][0]),
                abs(gold_position[1] - move[1][1])
            )
        )

        return [best_direction]


players = [BaselineBot()]
# The simulator imports this list and adds all contained bots to the game.
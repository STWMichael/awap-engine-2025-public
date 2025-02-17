import math
from src.player import Player
from src.map import Map
from src.robot_controller import RobotController
from src.game_constants import (
    Team,
    Tile,
    GameConstants,
    Direction,
    BuildingType,
    UnitType,
)


class BotPlayer(Player):
    def init(self, map: Map):
        self.map = map

    def get_square_slots(self, cx: int, cy: int, game_map: Map, main_castle=False):
        slots = []
        for d in [2, 3, 4]:
            for dx in range(-d, d + 1):
                for dy in range(-d, d + 1):
                    if max(abs(dx), abs(dy)) == d:
                        x = cx + dx
                        y = cy + dy
                        if (
                            0 <= x < game_map.width
                            and 0 <= y < game_map.height
                            and (
                                game_map.tiles[x][y] == Tile.GRASS
                                or game_map.tiles[x][y] == Tile.SAND
                                or game_map.tiles[x][y] == Tile.BRIDGE
                            )
                        ):
                            if d == 4 and not main_castle:
                                if (
                                    self.attack_unit == UnitType.WARRIOR
                                    and min(abs(dx), abs(dy)) == 4
                                ):
                                    slots.append((x, y, UnitType.CATAPULT))
                                else:
                                    slots.append((x, y, self.attack_unit))
                            else:
                                slots.append((x, y, UnitType.LAND_HEALER_1))
        return slots

    # For a given unit and a list of slots, find the nearest slot (by Manhattan distance)
    # that is not already occupied by another allied unit of the same type.
    def find_nearest_slot(self, unit, slots, my_units, cx, cy, dx, dy):
        best_slot = None
        best_dist = -float("inf")
        best_dist_center = 0
        for x, y, utype in slots:
            if utype != unit.type:
                continue
            occupied = False
            for ally in my_units:
                if (
                    ally.id != unit.id
                    and ally.type == unit.type
                    and ally.x == x
                    and ally.y == y
                ):
                    occupied = True
                    break
            if occupied:
                continue
            dist_center = max(abs(x - cx), abs(y - cy))
            dist = dx * (x - unit.x) + dy * (y - unit.y)
            if dist_center > best_dist_center or (
                dist_center == best_dist_center and dist > best_dist
            ):
                best_dist_center = dist_center
                best_dist = dist
                best_slot = (x, y)
        return best_slot

    # Move a unit one step toward (target_x, target_y) if possible.
    def move_towards(self, rc: RobotController, unit, target_x: int, target_y: int):
        current_x, current_y = unit.x, unit.y
        dx = target_x - current_x
        dy = target_y - current_y
        step_x = 1 if dx > 0 else (-1 if dx < 0 else 0)
        step_y = 1 if dy > 0 else (-1 if dy < 0 else 0)
        for d in Direction:
            if d.dx == step_x and d.dy == step_y:
                if rc.can_move_unit_in_direction(unit.id, d):
                    rc.move_unit_in_direction(unit.id, d)
                break

    # Choose a farm location.
    # Among tiles valid for building FARM_1, choose the tile with the maximum minimum Manhattan distance
    # to any enemy unit and also ensure that this tile is at least Chebyshev distance 7 from any existing formation center.
    def choose_farm_location(
        self, rc: RobotController, enemy_units, existing_centers, game_map: Map
    ):
        best_location = None
        best_distance = -1
        for x in range(game_map.width):
            for y in range(game_map.height):
                if not rc.can_build_building(BuildingType.FARM_1, x, y):
                    continue
                # Ensure candidate is at least Chebyshev distance 7 away from each existing formation center.
                valid = True
                if not self.attack:
                    for cx, cy, bid in existing_centers:
                        if max(abs(x - cx), abs(y - cy)) < 9:
                            valid = False
                            break
                if not valid:
                    continue
                min_dist = float("inf")
                for enemy in enemy_units:
                    dist = max(abs(enemy.x - x), abs(enemy.y - y))
                    if dist < min_dist:
                        min_dist = dist
                if min_dist > best_distance:
                    best_distance = min_dist
                    best_location = (x, y)
        return best_location

    def determine_mode(
        self, rc: RobotController, ally_castle, enemy_castle, game_map: Map
    ):
        self.attack = max(
            abs(ally_castle.x - enemy_castle.x), abs(ally_castle.y - enemy_castle.y)
        ) <= 20 or (
            min(abs(game_map.width - ally_castle.x - 1), abs(ally_castle.x))
            + min(abs(game_map.height - ally_castle.y - 1), abs(ally_castle.y))
            >= 4
        )

    def play_turn(self, rc: RobotController):
        team = rc.get_ally_team()
        balance = rc.get_balance(team)
        my_units = rc.get_units(team)
        loc_to_units = {}
        for unit in my_units:
            loc_to_units[(unit.x, unit.y)] = unit
        my_buildings = rc.get_buildings(team)
        ally_castle_id = -1
        for building in my_buildings:
            if building.type == BuildingType.MAIN_CASTLE:
                ally_castle_id = rc.get_id_from_building(building)[1]
                break
        ally_castle = rc.get_building_from_id(ally_castle_id)
        if ally_castle is None:
            return
        enemy = rc.get_enemy_team()
        enemy_units = rc.get_units(enemy)
        enemy_castle_id = -1
        enemy_buildings = rc.get_buildings(enemy)
        for building in enemy_buildings:
            if building.type == BuildingType.MAIN_CASTLE:
                enemy_castle_id = rc.get_id_from_building(building)[1]
                break
        enemy_castle = rc.get_building_from_id(enemy_castle_id)
        if enemy_castle is None:
            return
        game_map = rc.get_map()
        # Identify our formation centers: our main castle and any built farms.
        formation_centers = []
        for building in my_buildings:
            if (
                building.type == BuildingType.MAIN_CASTLE
                or building.type == BuildingType.FARM_1
            ):
                formation_centers.append(
                    (building.x, building.y, rc.get_id_from_building(building)[1])
                )

        # If no formation center exists, there is nothing to do.
        if not formation_centers:
            return
        if rc.get_turn() == 1:
            self.determine_mode(rc, ally_castle, enemy_castle, game_map)
            self.spawn_cycle = [
                UnitType.WARRIOR,
                UnitType.WARRIOR,
                UnitType.WARRIOR,
                UnitType.LAND_HEALER_1,
                UnitType.LAND_HEALER_1,
            ]
            self.spawn_index = 0  # tracks the next unit to spawn
            self.attack_unit = (
                UnitType.WARRIOR
                if max(
                    abs(ally_castle.x - enemy_castle.x),
                    abs(ally_castle.y - enemy_castle.y),
                )
                > 17
                else UnitType.SWORDSMAN
            )
        if self.attack:
            # Spawn Phase: Always try to spawn the next unit in our cycle if possible.
            next_unit_type = self.spawn_cycle[self.spawn_index]
            if next_unit_type == UnitType.WARRIOR:
                # Spawn CATAPULTS if they have a ring of healers around their castle
                if enemy_units:
                    locs_present = [False, False, False, False]
                    for enemy_unit in enemy_units:
                        if (
                            enemy_unit.x == enemy_castle.x
                            and enemy_unit.y == enemy_castle.y - 1
                        ):
                            locs_present[0] = True
                        elif (
                            enemy_unit.x == enemy_castle.x
                            and enemy_unit.y == enemy_castle.y + 1
                        ):
                            locs_present[1] = True
                        elif (
                            enemy_unit.x == enemy_castle.x - 1
                            and enemy_unit.y == enemy_castle.y
                        ):
                            locs_present[2] = True
                        elif (
                            enemy_unit.x == enemy_castle.x + 1
                            and enemy_unit.y == enemy_castle.y
                        ):
                            locs_present[3] = True
                    if all(locs_present):
                        next_unit_type = UnitType.CATAPULT
            if rc.can_spawn_unit(next_unit_type, ally_castle_id):
                rc.spawn_unit(next_unit_type, ally_castle_id)
                self.spawn_index = (self.spawn_index + 1) % len(self.spawn_cycle)

            # Movement & Attack Phase: Loop through all allied units.
            for unit_id in rc.get_unit_ids(team):
                unit = rc.get_unit_from_id(unit_id)
                if unit is None:
                    continue

                # For any unit (or Warriors that didn't attack an enemy troop):
                # If the enemy castle still stands and the unit can attack it, attack.
                if enemy_castle_id in rc.get_building_ids(
                    enemy
                ) and rc.can_unit_attack_building(unit_id, enemy_castle_id):
                    rc.unit_attack_building(unit_id, enemy_castle_id)
                    continue

                # # Warriors: If enemy troop is in range, attack it.
                if unit.type == UnitType.WARRIOR:
                    enemy_troop_found = False
                    for enemy_unit in enemy_units:
                        if enemy_unit is not None and rc.can_unit_attack_unit(
                            unit_id, enemy_unit.id
                        ):
                            rc.unit_attack_unit(unit_id, enemy_unit.id)
                            enemy_troop_found = True
                            break
                    if enemy_troop_found:
                        continue
                    else:
                        for enemy_building in enemy_buildings:
                            if rc.can_unit_attack_building(unit_id, enemy_building.id):
                                rc.unit_attack_building(unit_id, enemy_building.id)
                                break

                # Healers: Heal all allied Warriors in range.
                if unit.type == UnitType.LAND_HEALER_1:
                    sorted_units = rc.get_units(team)
                    sorted_units.sort(
                        key=lambda u: u.health,
                    )
                    for ally in sorted_units:
                        # print(ally.health)
                        if ally.health == UnitType.WARRIOR.health:
                            break
                        ally_id = rc.get_id_from_unit(ally)[1]
                        if ally is not None:
                            if rc.can_heal_unit(unit_id, ally_id):
                                rc.heal_unit(unit_id, ally_id)
                    # After healing, do not proceed with other actions.

                # Otherwise, move the unit toward the enemy castle.
                possible_move_dirs = rc.unit_possible_move_directions(unit_id)
                possible_move_dirs.sort(
                    key=lambda d: rc.get_chebyshev_distance(
                        *rc.new_location(unit.x, unit.y, d),
                        enemy_castle.x,
                        enemy_castle.y,
                    )
                )
                best_dir = (
                    possible_move_dirs[0]
                    if len(possible_move_dirs) > 0
                    else Direction.STAY
                )
                if rc.can_move_unit_in_direction(unit_id, best_dir):
                    rc.move_unit_in_direction(unit_id, best_dir)
                # -------------------------------
            # Phase 2: Expansion Stage (balance >= 35)
            # -------------------------------
            # PRIORITY: BUILD FARM FIRST!
            # Locate the enemy castle.

            best_loc = self.choose_farm_location(
                rc, enemy_units, formation_centers, game_map
            )

            if best_loc is not None:
                rc.build_building(
                    BuildingType.FARM_1,
                    *best_loc,
                )

            # Count the number of allied farms.
            farm_count = sum(
                1
                for building in rc.get_buildings(team)
                if building.type == BuildingType.FARM_1
            )

            # Only if we have at least 5 farms and our balance is above the cost needed for a new farm, proceed to spawn SWORDSMAN.
            if farm_count >= 7:
                # For every FARM_1, attempt to spawn one SWORDSMAN (one spawn per building per round).
                for building in rc.get_buildings(team):
                    if building.type == BuildingType.FARM_1:
                        _, farm_id = rc.get_id_from_building(building)
                        if farm_id is None:
                            continue
                        if rc.can_spawn_unit(UnitType.SWORDSMAN, farm_id):
                            rc.spawn_unit(UnitType.SWORDSMAN, farm_id)

                # Now, order all allied SWORDSMAN to act.
                # They will attack enemy units (if in range, Chebyshev distance ≤ 1) or the enemy castle,
                # otherwise, they move toward the enemy castle.
                swordsman_ids = []
                for unit_id in rc.get_unit_ids(team):
                    unit = rc.get_unit_from_id(unit_id)
                    if unit and unit.type == UnitType.SWORDSMAN:
                        swordsman_ids.append(unit_id)

                if enemy_castle:
                    target_x, target_y = enemy_castle.x, enemy_castle.y
                    _, castle_id = rc.get_id_from_building(enemy_castle)
                    for s_id in swordsman_ids:
                        swordsman = rc.get_unit_from_id(s_id)
                        if not swordsman:
                            continue

                        # First, check for enemy units in attack range (Chebyshev distance ≤ 1).
                        enemy_units = rc.get_units(enemy)
                        attacked = False
                        for enemy_unit in enemy_units:
                            if (
                                rc.get_chebyshev_distance(
                                    swordsman.x, swordsman.y, enemy_unit.x, enemy_unit.y
                                )
                                <= 1
                            ):
                                _, enemy_id = rc.get_id_from_unit(enemy_unit)
                                if enemy_id is not None and rc.can_unit_attack_unit(
                                    s_id, enemy_id
                                ):
                                    rc.unit_attack_unit(s_id, enemy_id)
                                    attacked = True
                                    break
                        if attacked:
                            continue

                        # Next, if the enemy castle is in range, attack it.
                        if (
                            rc.get_chebyshev_distance(
                                swordsman.x, swordsman.y, target_x, target_y
                            )
                            <= 1
                        ):
                            if castle_id is not None and rc.can_unit_attack_building(
                                s_id, castle_id
                            ):
                                rc.unit_attack_building(s_id, castle_id)
                            continue

                        # Otherwise, move toward the enemy castle.
                        poss_dirs = rc.unit_possible_move_directions(s_id)
                        poss_dirs.sort(
                            key=lambda d: rc.get_chebyshev_distance(
                                *rc.new_location(swordsman.x, swordsman.y, d),
                                target_x,
                                target_y,
                            )
                        )
                        best_dir = poss_dirs[0] if poss_dirs else None
                        if best_dir and rc.can_move_unit_in_direction(s_id, best_dir):
                            rc.move_unit_in_direction(s_id, best_dir)
            return

        if len(formation_centers) >= math.sqrt(game_map.width * game_map.height) // 8:
            my_units.sort(
                key=lambda unit: rc.get_chebyshev_distance(
                    unit.x, unit.y, enemy_castle.x, enemy_castle.y
                )
                - rc.get_chebyshev_distance(
                    unit.x, unit.y, ally_castle.x, ally_castle.y
                )
            )
            for unit in my_units:
                # print(
                #     unit.x,
                #     unit.y,
                #     rc.get_chebyshev_distance(
                #         unit.x, unit.y, enemy_castle.x, enemy_castle.y
                #     )
                #     - rc.get_chebyshev_distance(
                #         unit.x, unit.y, ally_castle.x, ally_castle.y
                #     ),
                # )
                if (
                    rc.get_chebyshev_distance(
                        unit.x, unit.y, enemy_castle.x, enemy_castle.y
                    )
                    - rc.get_chebyshev_distance(
                        unit.x, unit.y, ally_castle.x, ally_castle.y
                    )
                    > game_map.width // 2
                ):
                    break
                _, unit_id = rc.get_id_from_unit(unit)
                # print(unit_id)
                # print(rc.get_id_from_unit(rc.get_unit_from_id(unit_id)))
                if enemy_castle_id in rc.get_building_ids(
                    enemy
                ) and rc.can_unit_attack_building(unit_id, enemy_castle_id):
                    rc.unit_attack_building(unit_id, enemy_castle_id)

                for enemy_unit in enemy_units:
                    if rc.can_unit_attack_unit(unit_id, enemy_unit.id):
                        rc.unit_attack_unit(unit_id, enemy_unit.id)
                        break

                possible_move_dirs = rc.unit_possible_move_directions(unit_id)
                possible_move_dirs.sort(
                    key=lambda dir: rc.get_chebyshev_distance(
                        *rc.new_location(unit.x, unit.y, dir),
                        enemy_castle.x,
                        enemy_castle.y,
                    )
                )

                best_dir = (
                    possible_move_dirs[0]
                    if len(possible_move_dirs) > 0
                    else Direction.STAY
                )  # least chebyshev dist direction

                if rc.can_move_unit_in_direction(unit_id, best_dir):
                    # print(f"Moving {unit_id} in direction {best_dir}")
                    rc.move_unit_in_direction(unit_id, best_dir)

        # ----- Formation Building Phase -----
        for center in formation_centers:
            cx, cy, bid = center
            min_dist = float("inf")
            for enemy in enemy_units + enemy_buildings:
                dist = max(abs(enemy.x - cx), abs(enemy.y - cy))
                if dist < min_dist:
                    min_dist = dist
            if (
                rc.get_building_from_id(bid).type == BuildingType.FARM_1
                and min_dist > 25
            ):
                continue
            valid_slots = self.get_square_slots(
                cx,
                cy,
                game_map,
                rc.get_building_from_id(bid).type == BuildingType.MAIN_CASTLE,
            )
            # print(valid_slots)
            att_cnt = 0
            def_cnt = 0
            rng_cnt = 0
            for x in range(cx - 4, cx + 5):
                for y in range(cy - 4, cy + 5):
                    if (x, y) in loc_to_units:
                        if loc_to_units[(x, y)].type == UnitType.LAND_HEALER_1:
                            def_cnt -= 1
                        elif loc_to_units[(x, y)].type == self.attack_unit:
                            att_cnt -= 1
                        else:
                            rng_cnt -= 1
            for x, y, utype in valid_slots:
                if utype == UnitType.LAND_HEALER_1:
                    def_cnt += 1
                elif utype == self.attack_unit:
                    att_cnt += 1
                else:
                    rng_cnt += 1
            if rng_cnt > 0:
                rc.spawn_unit(UnitType.CATAPULT, bid)
                print("CATAPULT SPAWNED")
            elif att_cnt > 0:
                rc.spawn_unit(self.attack_unit, bid)
                print(f"{self.attack_unit} SPAWNED")
            elif def_cnt > 0:
                rc.spawn_unit(UnitType.LAND_HEALER_1, bid)
                print("LAND_HEALER_1 SPAWNED")

        # ----- Attacking Phase -----
        # For each formation center, if an enemy unit is within a threshold (say, Manhattan distance <= 3),
        # command WARRIOR near that center to attack the closest enemy.
        for center in formation_centers:
            cx, cy, bid = center
            closest_enemy = None
            closest_dist = float("inf")
            for enemy_unit in enemy_units:
                dist = abs(enemy_unit.x - cx) + abs(enemy_unit.y - cy)
                if dist < closest_dist:
                    closest_dist = dist
                    closest_enemy = enemy_unit
            if closest_enemy is not None:
                # Command nearby WARRIOR (within distance 3 of the center) to attack.
                for unit in my_units:
                    if (
                        unit.type == self.attack_unit
                        or unit.type == UnitType.CATAPULT
                        and max(abs(unit.x - cx), abs(unit.y - cy)) <= 4
                    ):
                        if rc.can_unit_attack_unit(unit.id, closest_enemy.id):
                            rc.unit_attack_unit(unit.id, closest_enemy.id)
                        else:
                            attacked = False
                            for enemy_unit in enemy_units:
                                if rc.can_unit_attack_unit(unit.id, enemy_unit.id):
                                    rc.unit_attack_unit(unit.id, enemy_unit.id)
                                    attacked = True
                                    break
                            if not attacked:
                                for enemy_building in enemy_buildings:
                                    if rc.can_unit_attack_building(
                                        unit.id, enemy_building.id
                                    ):
                                        rc.unit_attack_building(
                                            unit.id, enemy_building.id
                                        )
                                        break

        # ----- Movement Phase -----
        # For each formation center, move formation units (WARRIOR and LAND_HEALER_1) toward the nearest unoccupied slot.
        for center in formation_centers:
            cx, cy, bid = center
            dx = enemy_castle.x - cx
            dy = enemy_castle.y - cy
            step_x = 1 if dx > 0 else (-1 if dx < 0 else 0)
            step_y = 1 if dy > 0 else (-1 if dy < 0 else 0)
            for unit in my_units:
                # Consider only units that are relatively close to this formation center.
                if max(abs(unit.x - cx), abs(unit.y - cy)) > 4:
                    continue
                # For healers, if an allied WARRIOR nearby is injured, attempt to heal first.
                if unit.type == UnitType.LAND_HEALER_1:
                    target_ally = None
                    lowest_ratio = 1.0
                    for ally in my_units:
                        ratio = ally.health / ally.type.health
                        if ratio < lowest_ratio and rc.can_heal_unit(unit.id, ally.id):
                            lowest_ratio = ratio
                            target_ally = ally
                    if target_ally:
                        rc.heal_unit(unit.id, target_ally.id)
                    for ally in my_units:
                        ratio = ally.health / ally.type.health
                        if ratio < lowest_ratio and rc.can_heal_unit(unit.id, ally.id):
                            lowest_ratio = ratio
                            target_ally = ally
                    if target_ally:
                        rc.heal_unit(unit.id, target_ally.id)
                        continue  # Healing takes priority.
                # Otherwise, move the unit toward the nearest unoccupied slot.
                target_slot = self.find_nearest_slot(
                    unit,
                    self.get_square_slots(
                        cx,
                        cy,
                        game_map,
                        rc.get_building_from_id(bid).type == BuildingType.MAIN_CASTLE,
                    ),
                    my_units,
                    cx,
                    cy,
                    step_x, 
                    step_y,
                )
                if target_slot is not None:
                    tx, ty = target_slot
                    self.move_towards(rc, unit, tx, ty)

        # ----- Farm Building Phase -----
        # When we have enough balance to build a farm, choose a tile that is the furthest (by Manhattan distance)
        # from any enemy unit (and that is valid for a farm) and build it.
        if balance >= BuildingType.FARM_1.cost:
            candidate = self.choose_farm_location(
                rc, enemy_units, formation_centers, game_map
            )
            if candidate is not None:
                fx, fy = candidate
                if rc.can_build_building(BuildingType.FARM_1, fx, fy):
                    rc.build_building(BuildingType.FARM_1, fx, fy)
        return

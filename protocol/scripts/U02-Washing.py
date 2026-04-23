from opentrons import protocol_api
import math


metadata = {
    "protocolName": "U02 - Cell Wash 96-well Plates",
    "author": "Lucas L & Rasmus T.C",
    "description": (
        "Remove supernatant, perform configurable wash cycles with NaCl, "
        "and resuspend cells. Supports 1-4 Deep-well 96-well plates."
    ),
    "apiLevel": "2.20",
}


def add_parameters(parameters):
    parameters.add_int(
        variable_name="num_plates",
        display_name="Number of plates",
        description="How many 96-well plates to process (1-4).",
        default=2,
        minimum=1,
        maximum=2,
    )
    parameters.add_int(
        variable_name="wash_steps",
        display_name="Number of wash steps",
        description="How many wash cycles to perform before final resuspension (1-4).",
        default=1,
        minimum=1,
        maximum=4,
    )
    parameters.add_int(
        variable_name="reuse_within_wash_cycle",
        display_name="Reuse tips",
        description=("1 = reuse tips; 0 = fresh tips"),
        default=0,
        minimum=0,
        maximum=1,
    )
    parameters.add_float(
        variable_name = "resuspension_uL",
        display_name = "Resuspension volume (uL)",
        default = 440,
        minimum = 100,
        maximum = 800
    )
    parameters.add_float(
        variable_name = "initial_volume",
        display_name = "Initial volume (uL)",
        default = 580,
        minimum = 200,
        maximum = 1000
    )
    for i in range(1, 7):
        parameters.add_bool(
            variable_name = f"col_{i}",
            display_name = f"Columns {i}", 
            default=(i in [1,2,3,4])
            )


def run(protocol: protocol_api.ProtocolContext):

    RESUSPENSION_UL = protocol.params.resuspension_uL
    INITIAL_UL = protocol.params.initial_volume
    
    max_vol = 300

    resuspend_num_dispenses = math.ceil(RESUSPENSION_UL / max_vol)
    resuspend_vol_per_dispense = round(RESUSPENSION_UL/resuspend_num_dispenses)
    
    selected_cols = []
    for i in range(1, 7):
        if getattr(protocol.params, f"col_{i}"):
            selected_cols.append(i - 1) 

    if not selected_cols:
        raise ValueError("No columns selected. Please enable at least one column.")
        

    # -------------------- Inputs --------------------
    num_plates = protocol.params.num_plates
    wash_steps = protocol.params.wash_steps

    reuse_within_wash_cycle = bool(protocol.params.reuse_within_wash_cycle)

    if not 1 <= num_plates <= 4:
        raise ValueError("num_plates must be between 1 and 3")
    if not 1 <= wash_steps <= 4:
        raise ValueError("wash_steps must be between 1 and 3")

    # -------------------- Deck layout --------------------
    plate_slots = [2,3][:num_plates]
    reservoir_slot = 1
    od_plate_slots = [5,6][:num_plates]
    candidate_tip_slots = [4,7,8,9,10]
    p20_tip_slot = 11


    #-------------------- Tip racks --------------------
    if reuse_within_wash_cycle:
        pickups_per_column = 2 + wash_steps  
    else:
        pickups_per_column = 2 + (2 * wash_steps) 

    main_wash_pickups = len(selected_cols) * num_plates * pickups_per_column

    pairs_per_plate = math.ceil(len(selected_cols) / 2)

    pooling_pickups = num_plates * pairs_per_plate
    od_prep_pickups = num_plates * pairs_per_plate


    total_column_pickups = main_wash_pickups + pooling_pickups + od_prep_pickups
    tip_racks_needed = math.ceil(total_column_pickups / 12)

    tip_slots = candidate_tip_slots[:tip_racks_needed]

    if not tip_slots:
        raise ValueError("No deck slots available for tip racks with current configuration.")
    

    # --- Lab ware ---
    plates = [
        protocol.load_labware("nest_96_wellplate_2ml_deep", slot) for slot in plate_slots
    ]
    for i, slot in enumerate(plate_slots):
        protocol.comment(f"Loaded plate {i + 1} at slot {slot}")

    tipracks = [
        protocol.load_labware("opentrons_96_tiprack_300ul", slot) for slot in tip_slots
    ]
    for i, slot in enumerate(tip_slots):
        protocol.comment(f"Loaded tip rack {i + 1} at slot {slot}")

    od_plates = [
        protocol.load_labware("nest_96_wellplate_200ul_flat", slot) for slot in od_plate_slots
    ]
    for i, slot in enumerate(od_plate_slots):
        protocol.comment(f"Loaded OD plate {i + 1} at slot {slot}")

    p20_tips = protocol.load_labware("opentrons_96_tiprack_20ul", p20_tip_slot)
    reservoir = protocol.load_labware("axygen_1_reservoir_90ml", reservoir_slot)
    nacl = reservoir.wells()[0]

    pipette = protocol.load_instrument("p300_multi_gen2", "right", tip_racks = tipracks)
    p20 = protocol.load_instrument("p20_multi_gen2", mount = "left", tip_racks = [p20_tips])

    protocol.comment(
        f"Run setup: plates={num_plates}, wash_steps={wash_steps}, "
        f"reuse_within_wash_cycle={int(reuse_within_wash_cycle)}, "
        f"estimated_tips={total_column_pickups * 8} "
        f"({total_column_pickups} multichannel pickups)."
    )

    # -------------------- Helpers --------------------
    def column_tips_left() -> int:
        """Return how many full columns are available across all tip racks."""
        
        columns_left = 0
        for rack in tipracks:
            
            for col in rack.columns():
                if all(well.has_tip for well in col):
                    columns_left += 1
        return columns_left

    def ensure_tips(step_label: str, pickups_needed: int):
        remaining = column_tips_left()
        if remaining >= pickups_needed:
            protocol.comment(
                f"{step_label}: OK - {remaining} column pickups available (need {pickups_needed})."
            )
            return

        deficit = pickups_needed - remaining
        racks_to_reload = math.ceil(deficit / 12)
        reload_slots = tip_slots[:racks_to_reload]

        protocol.pause(
            f"{step_label}: need {pickups_needed} column pickups, only {remaining} available.\n"
            f"Reload {racks_to_reload} tip rack(s) in slots {reload_slots}, then resume."
        )

        for rack, slot in zip(tipracks, tip_slots):
            if slot in reload_slots:
                rack.reset()

        protocol.comment(
            f"Tip racks reloaded. Now {column_tips_left()} column pickups available."
        )

    def pick_up_fresh_column_tip():
        """Pick a fresh tip from row A to guarantee retrievable parking location."""
        for rack in tipracks:
            for tip in rack.rows()[0]:
                if tip.has_tip:
                    pipette.pick_up_tip(tip)
                    return tip
        raise RuntimeError("No fresh column tips available.")

    def remove_supernatant(volume_ul: float, label: str):
        protocol.comment(label)
        
        num_dispenses_actual = math.ceil(volume_ul / max_vol)
        vol_per_dispense_actual = round(volume_ul / num_dispenses_actual)
        
        for plate_index, plate in enumerate(plates):
            for col in selected_cols:
                pipette.pick_up_tip()
                for _ in range(num_dispenses_actual):
                    pipette.aspirate(vol_per_dispense_actual, plate.columns()[col][0].bottom(2))
                    pipette.dispense(vol_per_dispense_actual, protocol.fixed_trash)
                pipette.drop_tip()
            protocol.comment(f"{label}: plate {plate_index + 1} complete")

    def add_nacl_and_mix(
        volume_ul: float, mix_reps: int, mix_volume_ul: float, label: str
    ):
        protocol.comment(label)
        for plate_index, plate in enumerate(plates):
            for col in selected_cols:
                pipette.pick_up_tip()
                dest = plate.columns()[col][0]
                
                if volume_ul <= 300:
                    pipette.aspirate(volume_ul, nacl.bottom(0))
                    pipette.dispense(volume_ul, dest)
                else:
                    num_dispenses = math.ceil(volume_ul / 300)
                    vol_per_dispense = round(volume_ul / num_dispenses)
                    for _ in range(num_dispenses):
                        pipette.aspirate(vol_per_dispense, nacl.bottom(1))
                        pipette.dispense(vol_per_dispense, dest.bottom(1))

                if mix_reps > 0 and mix_volume_ul > 0:
                    pipette.mix(mix_reps, mix_volume_ul, dest)
                pipette.drop_tip()
            protocol.comment(f"{label}: plate {plate_index + 1} complete")

    def run_wash_cycle_paired_tip_reuse(cycle: int, total_cycles: int):
        protocol.comment(
            f"Wash cycle {cycle}/{total_cycles}: Add NaCl (paired tip reuse)"
        )
        parked_tips = []

        for plate_index, plate in enumerate(plates):
            for col in selected_cols:
                park_loc = pick_up_fresh_column_tip()
                dest = plate.columns()[col][0]
                for _ in range(resuspend_num_dispenses):
                    pipette.aspirate(resuspend_vol_per_dispense, nacl.bottom(0))
                    pipette.dispense(resuspend_vol_per_dispense, dest)
                pipette.mix(2, 50, dest)
                pipette.drop_tip(park_loc)
                parked_tips.append((plate_index, col, park_loc))
            protocol.comment(
                f"Wash cycle {cycle}/{total_cycles}: addition complete for plate {plate_index + 1}"
            )

        protocol.comment(
            f"Step 2.{cycle}b: Manual centrifugation for wash cycle {cycle}."
        )
        protocol.pause(
            f"Wash cycle {cycle}: centrifuge plate(s) to pellet cells, then return to robot."
        )

        protocol.comment(
            f"Wash cycle {cycle}/{total_cycles}: Remove wash supernatant (paired tip reuse)"
        )
        for plate_index, col, park_loc in parked_tips:
            plate = plates[plate_index]
            pipette.pick_up_tip(park_loc)
            pipette.aspirate(150, plate.columns()[col][0].bottom(2))
            pipette.drop_tip()
        protocol.comment(f"Wash cycle {cycle}/{total_cycles}: removal complete")

    def pool_replicate_pairs(plates, selected_cols, pipette, max_vol=300):
        if len(selected_cols) < 2:
            protocol.comment("Nothing to pool")
            return 

        
        selected_cols = sorted(selected_cols)

        for plate_index, plate in enumerate(plates):
            protocol.comment(f"Pooling replicate pairs on plate {plate_index+1}")
            
            for i in range(0, len(selected_cols), 2):
                source_col = selected_cols[i + 1]  
                target_col = selected_cols[i]      
                protocol.comment(f"Pooling column {source_col+1} into column {target_col+1}")

                
                volume_to_transfer = RESUSPENSION_UL
                num_transfers = math.ceil(volume_to_transfer / max_vol)
                vol_per_transfer = round(volume_to_transfer / num_transfers)

                pipette.pick_up_tip()
                for _ in range(num_transfers):
                    pipette.aspirate(vol_per_transfer, plate.columns()[source_col][0].bottom(2))
                    pipette.dispense(vol_per_transfer, plate.columns()[target_col][0].bottom(2))
                
                pipette.mix(3, 100, plate.columns()[target_col][0])
                pipette.drop_tip()
    
    def od_preparation(plates, od_plates, selected_cols, max_vol=300):
        """Prepare OD measurement plates with 100x dilution.
        
        For each pooled sample:
        1. Add 198 µL NaCl to OD plate wells (reusing single tip)
        2. Transfer 2 µL pooled culture for 100x dilution
        3. Mix thoroughly
        """
        pooled_cols = sorted(selected_cols)[::2]  
        
        for plate_index, (source_plate, od_plate) in enumerate(zip(plates, od_plates)):
            protocol.comment(f"OD prep: plate {plate_index + 1} - adding NaCl")
            
            
            pipette.pick_up_tip()
            for col_index in pooled_cols:
                dest_well = od_plate.columns()[col_index][0]
                pipette.aspirate(198, nacl.bottom(1))
                pipette.dispense(198, dest_well)
            pipette.drop_tip()
            
            protocol.comment(f"OD prep: plate {plate_index + 1} - Transferring cultures")
            
            
            for col_index in pooled_cols:
                source_well = source_plate.columns()[col_index][0]  
                dest_well = od_plate.columns()[col_index][0]
                p20.pick_up_tip()
                p20.aspirate(2, source_well.bottom(1))
                p20.dispense(2, dest_well.center())
                p20.mix(3, 10, dest_well)
                p20.touch_tip(speed=5)
                p20.drop_tip()
            
            protocol.comment(f"OD prep: plate {plate_index + 1} complete")
           
    # -------------------- Protocol --------------------
    protocol.comment("=== Washing Start ===")
    protocol.comment("Step 0: Pre-check - confirm plates were centrifuged to pellet cells.")
    protocol.pause("Did you spin down the plates to pellet the cells?")

    protocol.comment("Checking available tips for entire protocol execution.")
    ensure_tips("Protocol start - Total tips needed", pickups_needed=total_column_pickups)

    protocol.comment("Step 1: Remove starting supernatant from all plates.")
    remove_supernatant(INITIAL_UL, "Step 1: Remove starting supernatant")

    for cycle in range(1, wash_steps + 1):
        protocol.comment(f"Step 2.{cycle}a: Add NaCl for wash cycle {cycle}.")
        if reuse_within_wash_cycle:
            run_wash_cycle_paired_tip_reuse(cycle, wash_steps)
        else:
            add_nacl_and_mix(
                RESUSPENSION_UL,
                mix_reps=2,
                mix_volume_ul=100,
                label=f"Wash cycle {cycle}/{wash_steps}: Add NaCl",
            )

            protocol.comment(
                f"Step 2.{cycle}b: Manual centrifugation for wash cycle {cycle}."
            )
            protocol.pause(
                f"Wash cycle {cycle}: centrifuge plate(s) to pellet cells, then return to robot."
            )

            protocol.comment(
                f"Step 2.{cycle}c: Remove wash supernatant for wash cycle {cycle}."
            )
            remove_supernatant(
                RESUSPENSION_UL,
                label=f"Wash cycle {cycle}/{wash_steps}: Remove wash supernatant",
            )
    

    protocol.comment("Step 3: Adding fresh NaCl and resuspending cells.")
    add_nacl_and_mix(
        RESUSPENSION_UL,
        mix_reps=2,
        mix_volume_ul=100,
        label="Add fresh NaCl and resuspend",
    )

    protocol.pause("Did you shake the plates to ensure pellet dispersion?")

    protocol.comment("Step 4: Pool replicate columns pairwise")
    pool_replicate_pairs(plates, selected_cols, pipette)

    protocol.comment("Step 5: 100x dilution OD plate preparation.")
    od_preparation(plates, od_plates, selected_cols)

    protocol.comment("Protocol complete. Remove plates.")
    protocol.comment("=== Washing complete ===")
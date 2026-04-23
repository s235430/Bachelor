from opentrons import protocol_api

metadata = {
    "protocolName": "U04-Transfer - Solid",
    "author": "Rasmus T.C",
    "description": "Take 180 µL from reservoir + 20 µL from selected source columns and distribute to replicate destination columns. Spaced between source columns",
    "apiLevel": "2.20",
}

def add_parameters(parameters):
    for i in range(1, 13):  # 12 source columns max
        parameters.add_bool(
            variable_name=f"col_{i}",
            display_name=f"Source column {i}",
            default = i in [1,3]
        )

def run(protocol: protocol_api.ProtocolContext):

    REPLICATES_PER_SOURCE = 4

    # ----- Labware -----
    reservoir = protocol.load_labware("axygen_1_reservoir_90ml", 6)
    source_plate = protocol.load_labware("nest_96_wellplate_2ml_deep", 2)
    dest_plate = protocol.load_labware("nest_96_wellplate_200ul_flat", 3)
    tiprack = protocol.load_labware("opentrons_96_tiprack_300ul", 5)

    # ----- Instruments -----
    p300 = protocol.load_instrument("p300_multi_gen2", mount="right", tip_racks=[tiprack])

    # ----- Parameters -----
    selected_cols = [i for i in range(1, 13) if getattr(protocol.params, f"col_{i}")]
    if not selected_cols:
        raise ValueError("No columns selected. Please enable at least one column.")

    reservoir_well = reservoir.wells_by_name()['A1'] 

    dest_cols = []
    current_dest_col = 0
    for src_col in selected_cols:
        for _ in range(REPLICATES_PER_SOURCE):
            dest_cols.append((src_col, current_dest_col))
            current_dest_col += 1
        current_dest_col += 1

    p300.pick_up_tip()
    for _, dst_col_idx in dest_cols:
        dst_well = dest_plate.columns()[dst_col_idx][0]
        p300.aspirate(50, reservoir_well)
        p300.dispense(50, dst_well)
    p300.drop_tip()

    for src_col, dst_col_idx in dest_cols:
        src_well = source_plate.columns()[src_col - 1][0]
        dst_well = dest_plate.columns()[dst_col_idx][0]

        p300.pick_up_tip()
        p300.aspirate(180, src_well)
        p300.dispense(20, dst_well)
        p300.mix(2, 50, dst_well)
        p300.blow_out(dst_well.top())
        p300.drop_tip()
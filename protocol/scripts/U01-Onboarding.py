from opentrons import protocol_api
import math

metadata = {
    "protocolName": "U01-Onboarding: Onboarding from culture collection in a columnwise manner (2 µL 96→96 plating)",
    "author": "Rasmus Tøffner-Clausen",
    "description": (
        "Unit operation for onboarding strains from a culture collection by "
        "dispensing LB into 96-well destination plates and transferring 6 µL "
        "from source plates using multichannel pipettes."
    ),
    "apiLevel": "2.20",
}

# Api version 2.21 max

def add_parameters(parameters):
    parameters.add_float(
        variable_name="media_dispense_ul",
        display_name="Media dispense volume (uL)",
        description="Media volume dispensed into each destination well.",
        default=594,
        minimum=1.0,
        maximum=800,
    )
    parameters.add_float(
        variable_name="inoculation_ul",
        display_name="Inoculation volume (uL)",
        description="Inoculation volume transferred from source to destination.",
        default=6,
        minimum=2,
        maximum=20.0,
    )

    for i in range(1, 7):
        parameters.add_bool(
            variable_name = f"col_{i}",
            display_name = f"Source column {i}", 
            default=(i == 1))
        

def run(protocol: protocol_api.ProtocolContext):

    selected_cols = []
    for i in range(1,7):
        if getattr(protocol.params, f"col_{i}"):
            selected_cols.append(i)

    if not selected_cols:
            raise ValueError("No columns selected. Please enable at least one column.")
    
    REPLICATES = 2    
    MEDIA_DISPENSE_UL = float(protocol.params.media_dispense_ul)
    INOCULATION_UL = float(protocol.params.inoculation_ul)
    
    max_vol = 300
    num_dispenses = math.ceil(MEDIA_DISPENSE_UL / max_vol)
    vol_per_dispense = MEDIA_DISPENSE_UL/num_dispenses

    # ----- Deck plan -----
    plates_needed = math.ceil(len(selected_cols) * REPLICATES / 12)
    source_plate_slot = 2
    dest_plate_slots = [5, 6][:plates_needed]
    p20_tiprack_slots = [7, 8, 9][:plates_needed]
    p300_tiprack_slot = 10
    reservoir_slot = 11 if plates_needed < 3 else 6

    # ----- Lab ware -----
    reservoir = protocol.load_labware("axygen_1_reservoir_90ml", reservoir_slot)
    TY = reservoir.wells()[0]

    source_plate = protocol.load_labware("nest_96_wellplate_200ul_flat",source_plate_slot)

    dest_plates = []
    for i, slot in enumerate(dest_plate_slots):
        plate = protocol.load_labware(
            "nest_96_wellplate_2ml_deep",
            slot,
            label=f"DEST plate {i + 1}",
        )
        dest_plates.append(plate)
        protocol.comment(f"Loaded DESTINATION plate {i + 1} at slot {slot}")

    # Load tip racks
    p20_tipracks = []
    for i, slot in enumerate(p20_tiprack_slots):
        tr = protocol.load_labware("opentrons_96_tiprack_20ul", slot)
        p20_tipracks.append(tr)
        protocol.comment(f"Loaded P20 tip rack {i + 1} at slot {slot}")

    if p300_tiprack_slot not in p20_tiprack_slots:
        p300_tiprack = protocol.load_labware(
            "opentrons_96_tiprack_300ul", p300_tiprack_slot
        )
        protocol.comment(f"Loaded P300 tip rack at slot {p300_tiprack_slot}")
        p300_tipracks = [p300_tiprack]
    else:
        p300_tipracks = p20_tipracks

    # ----- Instruments -----
    p300 = protocol.load_instrument(
        "p300_multi_gen2", mount="right", tip_racks=p300_tipracks
    )
    p20 = protocol.load_instrument(
        "p20_multi_gen2", mount="left", tip_racks=p20_tipracks
    )

    total_dest_cols = len(selected_cols) * REPLICATES
    for plate_idx, dest in enumerate(dest_plates):
        p300.pick_up_tip() 

        p300.aspirate(100, TY.bottom(1))
        p300.dispense(100, TY.top())

        for col in range(12):
                global_col_index = plate_idx * 12 + col
                if global_col_index >= total_dest_cols:
                    break

                dst = dest.columns()[col][0]

                # Split into multiple aspirate/dispense only if volume > 300 µL
                if MEDIA_DISPENSE_UL <= 300:
                    p300.aspirate(MEDIA_DISPENSE_UL, TY.bottom(1))
                    p300.dispense(MEDIA_DISPENSE_UL, dst)
                else:
                    num_dispenses = math.ceil(MEDIA_DISPENSE_UL / 300)
                    vol_per_dispense = MEDIA_DISPENSE_UL / num_dispenses
                    for _ in range(num_dispenses):
                        p300.aspirate(vol_per_dispense, TY.bottom(1))
                        p300.dispense(vol_per_dispense, dst)

                p300.blow_out(dst.top())

        p300.drop_tip()

    
    dest_columns = []
    for plate in dest_plates:
        for col in plate.columns():
            dest_columns.append(col[0])

    transfer_columns = []
    for col in selected_cols:
        for _ in range(REPLICATES):
            transfer_columns.append(col - 1) 


    for i, src_col_idx in enumerate(transfer_columns):

        src = source_plate.columns()[src_col_idx][0] 
        dst = dest_columns[i]

        p20.flow_rate.aspirate = 5    
        p20.flow_rate.dispense = 5
        p20.flow_rate.blow_out = 10

        p20.pick_up_tip()

        p20.aspirate(INOCULATION_UL, src)
        p20.dispense(INOCULATION_UL, src)

        p20.aspirate(INOCULATION_UL, src)
        protocol.delay(seconds=2)

        p20.dispense(INOCULATION_UL, dst.bottom(1))
        protocol.delay(seconds=2)

        p20.mix(3, 10)


        p20.blow_out(dst.top())
        p20.touch_tip(speed=2.5)
        p20.drop_tip()

from opentrons import protocol_api
from collections import defaultdict

metadata = {
    "protocolName": "U04-Transfer - Liquid",
    "author": "Rasmus T.C",
    "description": (
        "Unit operation for transferring 20 µL from a 96-deepwell source plate "
        "to two 96-well destination plates using p20 pipette. "
        "Designed for ease of transfer out from source plate."
    ),
    "apiLevel": "2.20",
}


def add_parameters(parameters):
    parameters.add_csv_file(
        variable_name = "cherry_picks",
        display_name = "Randomized cherry pick csv",
        description = (
            "CSV: IBT #, from_well, to_well, media, plate, source_col"
        )
    )


def run(protocol: protocol_api.ProtocolContext):

    # ----- Labware -----
    source_plate = protocol.load_labware("nest_96_wellplate_2ml_deep", 2)
    dest_plate_l = protocol.load_labware("nest_96_wellplate_200ul_flat", 1)

    p20_triprack = [protocol.load_labware("opentrons_96_tiprack_20ul", 4)]
    
    p300_tipracks_slots = [5,6,9]
    
    p300_tipracks = [
    protocol.load_labware("opentrons_96_tiprack_300ul", slot)
    for slot in p300_tipracks_slots]

    
    reservoirs = protocol.load_labware("opentrons_tough_4_reservoir_72ml", 7)
    
    media_map = {
        "TY": reservoirs[0].wells_by_name()["A1"],
        "CRE": reservoirs[0].wells_by_name()["A2"],
        "LRE": reservoirs[0].wells_by_name()["A3"],
        "NaCl": reservoirs[0].wells_by_name()["A4"]
    }

    
    p300 = protocol.load_instrument("p300_single_gen2", mount="right", tip_racks=p300_tipracks)
    p20 = protocol.load_instrument("p20_single_gen2", mount="left", tip_racks=p20_triprack)
    
    csv_data = protocol.params.cherry_picks.parse_as_csv()
    runs = 0

    plates = defaultdict(list)
    headers = csv_data[0]

    # ----- Parameters -----
    for row in csv_data[1:]:
            row_dict = dict(zip(headers, row))
            plates[row_dict["plate"]].append(row_dict)

    for plate_id in sorted(plates.keys()):

        rows = plates[plate_id]

        if runs == 0:
            protocol.comment(f"Transfering to {plate_id}")
            runs += 1
        else:
            protocol.pause(f"First plates complete! Load tips and desination plates for {plate_id} and press resume")
            runs += 1
        protocol.comment("Filling wells with media")
        
        # -----------------------
        #        MEDIA FILL
        # -----------------------
        rows.sort(key=lambda r: r["media"])

        current_media = None
        p300.pick_up_tip()

        for row in rows:
            dest_well = dest_plate_l.wells_by_name()[row["to_well"]]
            media_type = row["media"]
            source_media = media_map[media_type]

            if media_type != current_media:
                if current_media is not None:
                    p300.drop_tip()
                    p300.pick_up_tip()

                current_media = media_type
                protocol.comment(f"filling from {source_media} with {current_media}")
                p300.aspirate(100, source_media)
                p300.dispense(100, source_media)

            p300.aspirate(180, source_media)
            p300.dispense(180, dest_well)
            p300.touch_tip(speed=5)

        p300.drop_tip()

        # -----------------------
        # P20 TRANSFER TO LIQUID
        # -----------------------

        grouped = defaultdict(list)
        for row in rows:
            key = (row["from_well"], row["media"])
            grouped[key].append(row)

        for (source_name, media_type), group in grouped.items():
            source_well = source_plate.wells_by_name()[source_name]

            p20.pick_up_tip()
            # Optional: mix once per strain before distributing
            p20.mix(2, 15, source_well)

            for row in group:
                dest_well = dest_plate_l.wells_by_name()[row["to_well"]]

                p20.aspirate(20, source_well.center())
                p20.dispense(20, dest_well)

            p20.drop_tip()
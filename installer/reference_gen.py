# -*- coding: utf-8 -*-
"""Erzeugt reference_calls.json (MS50-Umbau 2026) aus den abgenommenen Programm-
Listen und wendet sie optional auf eine DB an (Test).

Struktur reference_calls.json:
{
  "version": <int>,
  "merges": [[from_entity, into_entity], ...],   # Identitaets-Zusammenfuehrungen
  "dance_programs": [{code,label,sort_order,band,origin}, ...],
  "call_programs": [{entity_id, teaching_order, program}, ...]  # Ziel-Zustand Baender 10-50
}
Baender 60-100 (A2..C3b) werden NICHT angefasst.
"""
import json, sqlite3, sys, os

REFERENCE_DATA_VERSION = 3

MERGES = [
    ("call_walk_around_the_corner", "call_walk_around"),
    ("call_trade", "call_named_dancers_trade"),
]

# --- Programm-Listen (poslabel, [entity_ids]); slot=Ziffern, sub=Buchstabe(a=1..) ---
def parse(pl):
    i=0
    while i<len(pl) and pl[i].isdigit(): i+=1
    return int(pl[:i]), (ord(pl[i:])-96 if pl[i:] else 0)
def N(band,slot,sub): return round(band + slot/10000.0 + sub/1000000.0, 6)

MS50=[('1a',['call_circle_left','call_circle_right']),('1b',['call_circle_of_4']),('1c',['call_single_circle']),('2',['call_dosado']),('3a',['call_couples_promenade']),('3b',['call_single_file_promenade']),('3c',['call_star_promenade']),('3d',['call_wrong_way_promenade']),('4a',['call_arm_turns']),('4b',['call_allemande_left','call_allemande_right']),('5',['call_right_hand_star','call_left_hand_star']),('6a',['call_right_and_left_grand']),('6b',['call_weave_the_ring']),('6c',['call_wrong_way_grand']),('7',['call_pass_thru']),('8',['call_wheel_around','call_reverse_wheel_around']),('9',['call_courtesy_turn']),('10',['call_right_and_left_thru']),('11',['call_swing']),('12a',['call_two_ladies_chain']),('12b',['call_four_ladies_chain']),('12c',['call_chain_down_the_line']),('13a',['call_half_sashay']),('13b',['call_rollaway']),('13c',['call_ladies_in_men_sashay']),('14a',['call_u_turn_back']),('14b',['call_backtrack']),('15a',['call_separate']),('15b',['call_separate_around_to_a_line']),('15c',['call_separate_around_come_into_middle']),('16',['call_lead_right','call_lead_left']),('17',['call_veer_left','call_veer_right']),('18',['call_star_thru']),('19a',['call_couples_circulate']),('19b',['call_named_dancers_circulate']),('19c',['call_all_eight_circulate']),('19d',['call_single_file_circulate']),('19e',['call_split_circulate']),('20',['call_bend_the_line']),('21',['call_square_thru','call_left_square_thru']),('22',['call_split_two']),('23',['call_grand_square']),('24',['call_double_pass_thru']),('25',['call_first_go_next_go']),('26',['call_wheel_and_deal']),('27',['call_california_twirl']),('28',['call_slide_thru']),('29',['call_dive_thru']),('30',['call_box_the_gnat']),('31a',['call_alamo_style']),('31b',['call_balance']),('31c',['call_step_to_a_wave']),('31d',['call_dosado_to_a_wave']),('31e',['call_single_circle_to_a_wave']),('32a',['call_couples_trade']),('32b',['call_named_dancers_trade']),('32c',['call_right_hand_trade','call_left_hand_trade']),('32d',['call_partner_trade']),('33',['call_swing_thru','call_left_swing_thru']),('34',['call_run','call_cross_run']),('35',['call_pass_the_ocean']),('36',['call_extend']),('37',['call_flutterwheel','call_reverse_flutterwheel']),('38',['call_sweep_a_quarter']),('39',['call_trade_by']),('40',['call_ferris_wheel']),('41',['call_zoom']),('42',['call_touch_a_quarter']),('43a',['call_single_hinge']),('43b',['call_couples_hinge']),('44',['call_centers_in']),('45',['call_cast_off_three_quarters']),('46',['call_spin_the_top']),('47',['call_scoot_back']),('48',['call_fold','call_cross_fold']),('49a',['call_tag_the_line']),('49b',['call_fraction_tag']),('50',['call_recycle'])]

MSALT=[('1',['call_cloverleaf']),('2',['call_turn_thru']),('3',['call_eight_chain_thru']),('4',['call_pass_to_the_center']),('5a',['call_allemande_thar']),('5b',['call_allemande_left_to_allemande_thar']),('5c',['call_wrong_way_thar']),('6',['call_slip_the_clutch']),('7',['call_shoot_the_star']),('8a',['call_single_hinge']),('8b',['call_couples_hinge']),('9',['call_centers_in']),('10',['call_cast_off_three_quarters']),('11',['call_spin_the_top']),('12',['call_walk_and_dodge']),('13',['call_slide_thru']),('14',['call_fold','call_cross_fold']),('15',['call_dixie_style_to_a_wave']),('16',['call_spin_chain_thru']),('17a',['call_tag_the_line']),('17b',['call_fraction_tag']),('18',['call_scoot_back']),('19',['call_recycle'])]

PLUSALT_ORDER=['call_acey_deucey','call_spin_chain_the_gears','call_grand_swing_thru','call_triple_scoot','call_teacup_chain','call_ping_pong_circulate','call_load_the_boat','call_peel_off','call_coordinate','concept_anything_and_spread','call_track_2','concept_anything_and_roll','call_follow_your_neighbor','call_fan_the_top','call_dixie_grand','call_spin_chain_and_exchange_the_gears','call_explode_the_wave','concept_explode_and_anything','call_crossfire','call_relay_the_deucey','call_linear_cycle','call_peel_the_top','call_diamond_circulate','call_cut_the_diamond','call_single_circle_to_a_wave','call_trade_the_wave','call_flip_the_diamond','call_all_8_spin_the_top','call_chase_right']

PLUS26=[('1',['call_acey_deucey']),('2',['call_cloverleaf']),('3',['call_ping_pong_circulate']),('4',['call_turn_thru']),('5',['call_pass_to_the_center']),('6',['call_spin_chain_thru']),('7',['call_scoot_and_dodge']),('8',['call_pair_off']),('9',['call_teacup_chain']),('10',['call_dixie_style_to_a_wave']),('11',['call_walk_around']),('12',['call_see_saw']),('13',['call_load_the_boat']),('14a',['call_quarter_thru']),('14b',['call_three_quarter_thru']),('14c',['call_grand_quarter_thru']),('14d',['call_grand_three_quarter_thru']),('15',['call_walk_and_dodge']),('16',['call_spin_chain_the_gears']),('17',['call_grand_swing_thru']),('18',['call_triple_scoot']),('19',['call_track_2']),('20',['concept_anything_and_roll']),('21',['call_diamond_circulate']),('22',['call_pass_the_sea']),('23',['call_flip_the_diamond']),('24',['call_follow_your_neighbor']),('25',['call_cut_the_diamond']),('26a',['call_allemande_thar']),('26b',['call_allemande_left_to_allemande_thar']),('26c',['call_wrong_way_thar']),('27',['call_slip_the_clutch']),('28',['call_triple_trade']),('29',['call_shoot_the_star']),('30',['call_peel_off']),('31',['call_coordinate']),('32',['concept_anything_and_spread']),('33',['call_fan_the_top']),('34',['call_relay_the_deucey']),('35',['call_partner_tag']),('36',['call_dixie_grand']),('37',['call_explode_the_wave']),('38',['call_crossfire']),('39',['concept_explode_and_anything']),('40',['call_partner_hinge']),('41',['call_spin_chain_and_exchange_the_gears']),('42',['call_linear_cycle']),('43',['call_peel_the_top']),('44',['call_circle_to_a_line']),('45',['call_chase_right']),('46',['concept_clover_and_anything']),('47',['call_trade_the_wave']),('48',['call_eight_chain_thru']),('49',['call_all_8_spin_the_top']),('50',['call_do_paso'])]

A1ALT=[('1',['dancer_belle','dancer_beau']),('2',['call_brace_thru']),('3',['call_cross_trail_thru']),('4',['call_triple_trade']),('5',['call_grand_follow_your_neighbor']),('6',['call_quarter_thru']),('7',['call_wheel_thru']),('8',['call_turn_and_deal']),('9a',['call_pass_in']),('9b',['call_pass_out']),('10',['call_chain_reaction']),('11',['call_mix']),('12',['call_lockit']),('13',['call_roll_to_a_wave']),('14',['call_cast_a_shadow']),('15',['call_six_two_acey_deucey']),('16',['concept_clover_and_anything']),('17a',['call_quarter_in']),('17b',['call_quarter_out']),('18',['call_cross_over_circulate']),('19',['call_partner_tag']),('20',['call_partner_hinge']),('21',['call_horseshoe_turn']),('22',['call_pass_the_sea']),('23',['call_split_square_thru']),('24',['call_step_and_slide']),('25',['call_transfer_the_column']),('26',['call_swap_around']),('27',['call_explode_the_line']),('28',['concept_as_couples']),('29',['call_ends_bend']),('30',['call_square_chain_thru']),('31',['call_scoot_and_dodge']),('32',['call_double_star_thru']),('33',['call_left_wheel_thru']),('34',['call_anything_and_cross']),('35',['call_named_dancers_cross']),('36',['call_fractional_tops']),('37',['call_three_quarter_thru']),('38',['call_triple_star_thru']),('39',['call_cycle_and_wheel']),('40',['call_grand_quarter_thru']),('41',['call_grand_three_quarter_thru']),('42',['concept_explode_and_anything']),('43',['call_pair_off']),('44',['call_reverse_swap_around']),('45',['call_cross_clover_and_anything']),('46',['concept_any_hand']),('47',['call_split_square_chain_thru']),('48a',['call_triple_cross']),('48b',['call_double_cross'])]

def build(band, struct, slot_off=0, prog=""):
    out=[]
    for pl,eids in struct:
        s,sub=parse(pl)
        for e in eids:
            out.append({"entity_id":e,"teaching_order":N(band,s+slot_off,sub),"program":prog})
    return out

def apply_merges(cp_rows):
    m={a:b for a,b in MERGES}
    for r in cp_rows:
        if r["entity_id"] in m: r["entity_id"]=m[r["entity_id"]]
    return cp_rows

def main():
    src_db = sys.argv[1] if len(sys.argv)>1 else None
    call_programs=[]
    # Baender 10/20 aus DB (Basic, unveraendert) + FnB bleibt in 10
    if src_db:
        c=sqlite3.connect(src_db)
        for b in (10,20,60,70,80,90,100):
            for to,e in c.execute("SELECT teaching_order,entity_id FROM teaching_order_calls WHERE CAST(teaching_order AS INT)=? AND entity_id NOT LIKE 'separator%'",(b,)):
                call_programs.append({"entity_id":e,"teaching_order":round(to,6),"program":""})
        c.close()
    # neue/umgebaute Baender
    call_programs += build(30, MS50, prog="Mainstream (2026)")
    call_programs += [{"entity_id":"call_forward_and_back","teaching_order":30.000150,"program":"Mainstream (2026)"}]
    call_programs += build(29, MSALT, slot_off=48, prog="Mainstream")
    call_programs += build(39, [(str(i+1),[e]) for i,e in enumerate(PLUSALT_ORDER)], prog="Plus")
    call_programs += build(40, PLUS26, prog="Plus (2026)")
    call_programs += build(49, A1ALT, prog="Advanced 1")
    # Band 50 (A1 2026) aus DB uebernehmen (= A1 alt minus Wanderer, bereits so)
    if src_db:
        c=sqlite3.connect(src_db)
        for to,e in c.execute("SELECT teaching_order,entity_id FROM teaching_order_calls WHERE CAST(teaching_order AS INT)=50 AND entity_id NOT LIKE 'separator%'"):
            call_programs.append({"entity_id":e,"teaching_order":round(to,6),"program":"Advanced 1 (2026)"})
        c.close()
    call_programs = apply_merges(call_programs)
    # Duplikate (entity,to) zusammenfassen
    seen={};
    for r in call_programs:
        seen[(r["entity_id"],r["teaching_order"])]=r
    call_programs=list(seen.values())

    # Reihenfolge je Familie: alt -> (2026) -> (Class). Class-Programme teilen sich
    # das Band ihres 2026-/Basis-Programms (= gleiche Calls) und tragen is_class=True.
    # Class-Codes mit Leerzeichen ("MS Class"), passend zu _DEFAULT_DANCE_PROGRAMS.
    dance_programs=[
        {"code":"BASIC1","label":"Basic 1","band":10},
        {"code":"BASIC2","label":"Basic 2","band":20},
        {"code":"MS","label":"Mainstream","band":29},
        {"code":"MS2026","label":"Mainstream (2026)","band":30},
        {"code":"MS Class","label":"Mainstream (Class)","band":30,"is_class":True},
        {"code":"PL","label":"Plus","band":39},
        {"code":"PL2026","label":"Plus (2026)","band":40},
        {"code":"PL Class","label":"Plus (Class)","band":40,"is_class":True},
        {"code":"A1","label":"Advanced 1","band":49},
        {"code":"A1_2026","label":"Advanced 1 (2026)","band":50},
        {"code":"A1 Class","label":"Advanced 1 (Class)","band":50,"is_class":True},
        {"code":"A2","label":"Advanced 2","band":60},
        {"code":"A2 Class","label":"Advanced 2 (Class)","band":60,"is_class":True},
        {"code":"C1","label":"Challenge 1","band":70},
        {"code":"C1 Class","label":"Challenge 1 (Class)","band":70,"is_class":True},
        {"code":"C2","label":"Challenge 2","band":80},
        {"code":"C2 Class","label":"Challenge 2 (Class)","band":80,"is_class":True},
        {"code":"C3A","label":"Challenge 3A","band":90},
        {"code":"C3A Class","label":"Challenge 3A (Class)","band":90,"is_class":True},
        {"code":"C3B","label":"Challenge 3B","band":100},
    ]
    for i,dp in enumerate(dance_programs):
        dp["sort_order"]=(i+1)*10; dp["origin"]="builtin"

    # Programm-Trenner (-- Label --) je Band bei band.999999, wie im alten Bestand.
    # Nur fuer Primaer-Programme — Class-Varianten teilen sich das Band (kein
    # zweiter Trenner je Band).
    for dp in dance_programs:
        if dp.get("is_class"):
            continue
        b=int(dp["band"])
        call_programs.append({"entity_id":f"separator_{b}",
                              "teaching_order":round(b+0.999999,6),
                              "program":dp["label"],
                              "canonical_name":f"-- {dp['label']} --"})

    # canonical_name an jede Zeile haengen (self-contained fuer den Reseed).
    namemap={}
    if src_db:
        c=sqlite3.connect(src_db)
        for e,n in c.execute("SELECT entity_id,canonical_name FROM teaching_order_calls"):
            namemap[e]=n
        c.close()
    namemap["call_forward_and_back"]=namemap.get("call_forward_and_back","Forward and Back")
    for r in call_programs:
        if "canonical_name" not in r:
            r["canonical_name"]=namemap.get(r["entity_id"], r["entity_id"])

    doc={"version":REFERENCE_DATA_VERSION,"merges":MERGES,"dance_programs":dance_programs,"call_programs":call_programs}
    outp=os.path.join(os.path.dirname(__file__),"reference_calls.json")
    json.dump(doc, open(outp,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"reference_calls.json: {len(call_programs)} call_programs, {len(dance_programs)} programs -> {outp}")
    from collections import Counter
    print("Baender:", dict(sorted(Counter(int(r['teaching_order']) for r in call_programs).items())))

if __name__=="__main__":
    main()

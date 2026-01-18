import os
from decimal import Decimal, InvalidOperation
from datetime import date

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev_secret_change_me")

DB_NAME = os.environ.get("DB_NAME", "upravljanje_najmovima")
DB_USER = os.environ.get("DB_USER", "app_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app_pass")
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))


def get_conn():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        cursor_factory=RealDictCursor,
    )


def dec(val: str) -> Decimal:
    try:
        return Decimal(val)
    except (InvalidOperation, TypeError):
        raise ValueError("Neispravan broj.")


@app.route("/")
def index():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT osvjezi_status_isteklih_ugovora() AS n;")
            osvjezeno = cur.fetchone()["n"]

            cur.execute(
                """
                SELECT
                    ugovor_id, datum_pocetka, datum_zavrsetka, mjesecna_najamnina, polog,
                    adresa, tip_nekretnine, povrsina,
                    vlasnik_ime_prezime, najmoprimac_ime_prezime,
                    trenutni_status
                FROM v_aktivni_ugovori
                ORDER BY ugovor_id;
                """
            )
            ugovori = cur.fetchall()

    return render_template("ugovori_aktivni.html", ugovori=ugovori, osvjezeno=osvjezeno)


@app.route("/svi_ugovori")
def svi_ugovori():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    u.ugovor_id,
                    u.datum_pocetka,
                    u.datum_zavrsetka,
                    u.mjesecna_najamnina,
                    u.polog,
                    u.napomena,
                    n.nekretnina_id,
                    n.adresa,
                    n.tip_nekretnine,
                    n.povrsina,
                    v.korisnik_id AS vlasnik_id,
                    (v.ime || ' ' || v.prezime) AS vlasnik_ime_prezime,
                    t.korisnik_id AS najmoprimac_id,
                    (t.ime || ' ' || t.prezime) AS najmoprimac_ime_prezime,
                    ts.status AS trenutni_status
                FROM ugovor_najma u
                JOIN nekretnina n ON n.nekretnina_id = u.nekretnina_id
                JOIN korisnik v ON v.korisnik_id = n.vlasnik_id
                JOIN korisnik t ON t.korisnik_id = u.najmoprimac_id
                JOIN v_trenutni_status_ugovora ts ON ts.ugovor_id = u.ugovor_id
                ORDER BY u.ugovor_id;
                """
            )
            ugovori = cur.fetchall()
    return render_template("ugovori_svi.html", ugovori=ugovori)


@app.route("/ugovor/novi", methods=["GET", "POST"])
def novi_ugovor():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT nekretnina_id, adresa FROM nekretnina ORDER BY nekretnina_id;")
            nekretnine = cur.fetchall()

            cur.execute(
                """
                SELECT korisnik_id, (ime || ' ' || prezime) AS ime_prezime
                FROM korisnik
                ORDER BY korisnik_id;
                """
            )
            korisnici = cur.fetchall()

            if request.method == "POST":
                try:
                    nekretnina_id = int(request.form["nekretnina_id"])
                    najmoprimac_id = int(request.form["najmoprimac_id"])
                    datum_pocetka = request.form["datum_pocetka"]
                    datum_zavrsetka = request.form["datum_zavrsetka"]
                    mjesecna_najamnina = dec(request.form["mjesecna_najamnina"])
                    polog = dec(request.form.get("polog", "0") or "0")
                    napomena = request.form.get("napomena") or None

                    cur.execute(
                        """
                        INSERT INTO ugovor_najma
                            (nekretnina_id, najmoprimac_id, datum_pocetka, datum_zavrsetka,
                             mjesecna_najamnina, polog, napomena)
                        VALUES
                            (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING ugovor_id;
                        """,
                        (nekretnina_id, najmoprimac_id, datum_pocetka, datum_zavrsetka, mjesecna_najamnina, polog, napomena),
                    )
                    ugovor_id = cur.fetchone()["ugovor_id"]
                    conn.commit()
                    flash(f"Ugovor #{ugovor_id} uspješno dodan. Status AKTIVAN je automatski upisan (trigger).", "success")
                    return redirect(url_for("ugovor_detalji", ugovor_id=ugovor_id))
                except Exception as e:
                    conn.rollback()
                    flash(f"Greška pri unosu ugovora: {e}", "error")

    return render_template("ugovor_novi.html", nekretnine=nekretnine, korisnici=korisnici)


@app.route("/ugovor/<int:ugovor_id>")
def ugovor_detalji(ugovor_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    u.ugovor_id,
                    u.datum_pocetka,
                    u.datum_zavrsetka,
                    u.mjesecna_najamnina,
                    u.polog,
                    u.napomena,
                    n.adresa,
                    n.tip_nekretnine,
                    n.povrsina,
                    (v.ime || ' ' || v.prezime) AS vlasnik_ime_prezime,
                    (t.ime || ' ' || t.prezime) AS najmoprimac_ime_prezime,
                    ts.status AS trenutni_status
                FROM ugovor_najma u
                JOIN nekretnina n ON n.nekretnina_id = u.nekretnina_id
                JOIN korisnik v ON v.korisnik_id = n.vlasnik_id
                JOIN korisnik t ON t.korisnik_id = u.najmoprimac_id
                JOIN v_trenutni_status_ugovora ts ON ts.ugovor_id = u.ugovor_id
                WHERE u.ugovor_id = %s;
                """,
                (ugovor_id,),
            )
            ugovor = cur.fetchone()

    if not ugovor:
        flash("Ugovor ne postoji.", "error")
        return redirect(url_for("svi_ugovori"))

    return render_template("ugovor_detalji.html", ugovor=ugovor, today=date.today())


@app.route("/ugovor/<int:ugovor_id>/raskini", methods=["POST"])
def ugovor_raskini(ugovor_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT postavi_status_ugovora(%s, 'RASKINUT', CURRENT_DATE);", (ugovor_id,))
                conn.commit()
                flash(f"Ugovor #{ugovor_id} je raskinut. Status je upisan u povijest.", "success")
            except Exception as e:
                conn.rollback()
                flash(f"Greška pri raskidu ugovora: {e}", "error")
    return redirect(url_for("ugovor_detalji", ugovor_id=ugovor_id))


@app.route("/statusi/<int:ugovor_id>")
def statusi(ugovor_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ugovor_id, status, vrijedi_od, vrijedi_do
                FROM status_ugovora_povijest
                WHERE ugovor_id = %s
                ORDER BY vrijedi_od;
                """,
                (ugovor_id,),
            )
            rows = cur.fetchall()
    return render_template("statusi.html", ugovor_id=ugovor_id, rows=rows)


@app.route("/ugovor/<int:ugovor_id>/uplate")
def uplate(ugovor_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT uplata_id, iznos, datum_uplate, razdoblje
                FROM uplata
                WHERE ugovor_id = %s
                ORDER BY razdoblje, uplata_id;
                """,
                (ugovor_id,),
            )
            rows = cur.fetchall()
    return render_template("uplate.html", ugovor_id=ugovor_id, uplate=rows)


@app.route("/ugovor/<int:ugovor_id>/uplata/nova", methods=["GET", "POST"])
def uplata_nova(ugovor_id: int):
    if request.method == "POST":
        with get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    iznos = dec(request.form["iznos"])
                    datum_uplate = request.form["datum_uplate"]
                    razdoblje = request.form["razdoblje"]

                    cur.execute(
                        """
                        INSERT INTO uplata (ugovor_id, iznos, datum_uplate, razdoblje)
                        VALUES (%s, %s, %s, %s)
                        RETURNING uplata_id;
                        """,
                        (ugovor_id, iznos, datum_uplate, razdoblje),
                    )
                    uplata_id = cur.fetchone()["uplata_id"]
                    conn.commit()
                    flash(f"Uplata #{uplata_id} dodana.", "success")
                    return redirect(url_for("uplate", ugovor_id=ugovor_id))
                except Exception as e:
                    conn.rollback()
                    flash(f"Greška pri unosu uplate: {e}", "error")

    return render_template("uplata_forma.html", ugovor_id=ugovor_id)


@app.route("/korisnici")
def korisnici():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT korisnik_id, ime, prezime, email, tip_korisnika, to_char(datum_kreiranja, 'YYYY-MM-DD HH24:MI') AS datum_kreiranja
                FROM korisnik
                ORDER BY korisnik_id;
                """
            )
            rows = cur.fetchall()
    return render_template("korisnici.html", korisnici=rows)


@app.route("/korisnik/novi", methods=["GET", "POST"])
def korisnik_novi():
    if request.method == "POST":
        with get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    ime = (request.form.get("ime") or "").strip()
                    prezime = (request.form.get("prezime") or "").strip()
                    email = (request.form.get("email") or "").strip()
                    tip_korisnika = request.form.get("tip_korisnika")

                    cur.execute(
                        """
                        INSERT INTO korisnik (ime, prezime, email, tip_korisnika)
                        VALUES (%s, %s, %s, %s)
                        RETURNING korisnik_id;
                        """,
                        (ime, prezime, email, tip_korisnika),
                    )
                    korisnik_id = cur.fetchone()["korisnik_id"]
                    conn.commit()
                    flash(f"Korisnik #{korisnik_id} dodan.", "success")
                    return redirect(url_for("korisnici"))
                except Exception as e:
                    conn.rollback()
                    flash(f"Greška pri unosu korisnika: {e}", "error")

    return render_template("korisnik_forma.html", naslov="Novi korisnik", korisnik=None)


@app.route("/korisnik/<int:korisnik_id>/uredi", methods=["GET", "POST"])
def korisnik_uredi(korisnik_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT korisnik_id, ime, prezime, email, tip_korisnika
                FROM korisnik
                WHERE korisnik_id = %s;
                """,
                (korisnik_id,),
            )
            korisnik = cur.fetchone()

            if not korisnik:
                flash("Korisnik ne postoji.", "error")
                return redirect(url_for("korisnici"))

            if request.method == "POST":
                try:
                    ime = (request.form.get("ime") or "").strip()
                    prezime = (request.form.get("prezime") or "").strip()
                    email = (request.form.get("email") or "").strip()
                    tip_korisnika = request.form.get("tip_korisnika")

                    cur.execute(
                        """
                        UPDATE korisnik
                        SET ime=%s, prezime=%s, email=%s, tip_korisnika=%s
                        WHERE korisnik_id=%s;
                        """,
                        (ime, prezime, email, tip_korisnika, korisnik_id),
                    )
                    conn.commit()
                    flash(f"Korisnik #{korisnik_id} ažuriran.", "success")
                    return redirect(url_for("korisnici"))
                except Exception as e:
                    conn.rollback()
                    flash(f"Greška pri ažuriranju korisnika: {e}", "error")

    return render_template("korisnik_forma.html", naslov=f"Uredi korisnika #{korisnik_id}", korisnik=korisnik)


@app.route("/korisnik/<int:korisnik_id>/obrisi", methods=["POST"])
def korisnik_obrisi(korisnik_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM korisnik WHERE korisnik_id=%s;", (korisnik_id,))
                conn.commit()
                flash(f"Korisnik #{korisnik_id} obrisan.", "success")
            except Exception as e:
                conn.rollback()
                flash(f"Ne mogu obrisati korisnika (vjerojatno se koristi kao FK): {e}", "error")
    return redirect(url_for("korisnici"))


@app.route("/nekretnine")
def nekretnine():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    n.nekretnina_id,
                    n.adresa,
                    n.tip_nekretnine,
                    n.povrsina,
                    n.vlasnik_id,
                    (k.ime || ' ' || k.prezime) AS vlasnik_ime_prezime
                FROM nekretnina n
                JOIN korisnik k ON k.korisnik_id = n.vlasnik_id
                ORDER BY n.nekretnina_id;
                """
            )
            rows = cur.fetchall()
    return render_template("nekretnine.html", nekretnine=rows)


@app.route("/nekretnina/nova", methods=["GET", "POST"])
def nekretnina_nova():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT korisnik_id, (ime || ' ' || prezime) AS ime_prezime
                FROM korisnik
                ORDER BY korisnik_id;
                """
            )
            korisnici = cur.fetchall()

            if request.method == "POST":
                try:
                    adresa = (request.form.get("adresa") or "").strip()
                    tip_nekretnine = request.form.get("tip_nekretnine")
                    povrsina = dec(request.form.get("povrsina"))
                    vlasnik_id = int(request.form.get("vlasnik_id"))

                    cur.execute(
                        """
                        INSERT INTO nekretnina (adresa, tip_nekretnine, povrsina, vlasnik_id)
                        VALUES (%s, %s, %s, %s)
                        RETURNING nekretnina_id;
                        """,
                        (adresa, tip_nekretnine, povrsina, vlasnik_id),
                    )
                    nekretnina_id = cur.fetchone()["nekretnina_id"]
                    conn.commit()
                    flash(f"Nekretnina #{nekretnina_id} dodana.", "success")
                    return redirect(url_for("nekretnine"))
                except Exception as e:
                    conn.rollback()
                    flash(f"Greška pri unosu nekretnine: {e}", "error")

    return render_template("nekretnina_forma.html", naslov="Nova nekretnina", nekretnina=None, korisnici=korisnici)


@app.route("/nekretnina/<int:nekretnina_id>/uredi", methods=["GET", "POST"])
def nekretnina_uredi(nekretnina_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT nekretnina_id, adresa, tip_nekretnine, povrsina, vlasnik_id
                FROM nekretnina
                WHERE nekretnina_id=%s;
                """,
                (nekretnina_id,),
            )
            nekretnina = cur.fetchone()

            if not nekretnina:
                flash("Nekretnina ne postoji.", "error")
                return redirect(url_for("nekretnine"))

            cur.execute(
                """
                SELECT korisnik_id, (ime || ' ' || prezime) AS ime_prezime
                FROM korisnik
                ORDER BY korisnik_id;
                """
            )
            korisnici = cur.fetchall()

            if request.method == "POST":
                try:
                    adresa = (request.form.get("adresa") or "").strip()
                    tip_nekretnine = request.form.get("tip_nekretnine")
                    povrsina = dec(request.form.get("povrsina"))
                    vlasnik_id = int(request.form.get("vlasnik_id"))

                    cur.execute(
                        """
                        UPDATE nekretnina
                        SET adresa=%s, tip_nekretnine=%s, povrsina=%s, vlasnik_id=%s
                        WHERE nekretnina_id=%s;
                        """,
                        (adresa, tip_nekretnine, povrsina, vlasnik_id, nekretnina_id),
                    )
                    conn.commit()
                    flash(f"Nekretnina #{nekretnina_id} ažurirana.", "success")
                    return redirect(url_for("nekretnine"))
                except Exception as e:
                    conn.rollback()
                    flash(f"Greška pri ažuriranju nekretnine: {e}", "error")

    return render_template(
        "nekretnina_forma.html",
        naslov=f"Uredi nekretninu #{nekretnina_id}",
        nekretnina=nekretnina,
        korisnici=korisnici,
    )


@app.route("/nekretnina/<int:nekretnina_id>/obrisi", methods=["POST"])
def nekretnina_obrisi(nekretnina_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM nekretnina WHERE nekretnina_id=%s;", (nekretnina_id,))
                conn.commit()
                flash(f"Nekretnina #{nekretnina_id} obrisana.", "success")
            except Exception as e:
                conn.rollback()
                flash(f"Ne mogu obrisati nekretninu (vjerojatno se koristi u ugovoru): {e}", "error")
    return redirect(url_for("nekretnine"))


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)

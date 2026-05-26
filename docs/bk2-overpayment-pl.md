# Bezpieczny Kredyt 2% — mechanika nadpłat

Ten dokument wyjaśnia jak działa Bezpieczny Kredyt 2% (BK2%), czym różni się od zwykłego
kredytu hipotecznego, jak nadpłaty wpływają na dopłatę BGK i jak wygląda optymalna strategia
w zależności od tego, ile zostało do końca okresu dopłat.

To jest podstawa konceptualna dla funkcji `bk2_overpayment()` w `agent/tools/calculator.py`.

---

## 1. Zwykły kredyt hipoteczny (punkt odniesienia)

Standardowy polski kredyt hipoteczny ze zmienną stopą działa tak:

```
Rata miesięczna  = część kapitałowa + część odsetkowa
Część odsetkowa  = Ks × stopa / 12
```

Gdzie `Ks` to pozostałe saldo, a `stopa` to pełna stopa kontraktowa (np. WIRON 3M + marża
≈ 7–8%). Kredytobiorca płaci **pełną stopę od każdej złotówki** pozostałego salda przez cały
okres kredytowania.

**Nadpłata w zwykłym kredycie:**

Nadpłacając X PLN, zmniejszasz saldo o X. Co miesiąc płacisz mniej odsetek przy pełnej stopie.
Gwarantowany „zwrot" z nadpłaty = pełna stopa kredytu. Jeśli stopa to 7,5%, każda nadpłacona
złotówka oszczędza 7,5% rocznie. Porównanie jest proste: stopa kredytu vs zwrot z inwestycji
po podatku Belki.

---

## 2. Struktura BK2% — ogólny zarys

BK2% to kredyt dwufazowy. Fazy wyznacza okres dopłat, nie zmiany oprocentowania.

```
Faza 1  │  Pierwsze 120 rat spłaconych zgodnie z harmonogramem  │  BGK pokrywa spread ponad 2%
Faza 2  │  Pozostałe raty                                        │  Kredytobiorca płaci pełną stopę
```

Kredyt ma **stałą stopę przez pierwsze 120 miesięcy** (§2 ust. 15 warunków BGK), ustalana co
60 miesięcy. Stopa się nie zmienia — ale mechanika dopłat sprawia, że efektywny koszt dla
kredytobiorcy jest zupełnie inny w Fazie 1 i Fazie 2.

---

## 3. Faza 1: okres dopłat

### 3a. Typ amortyzacji — raty malejące

To najważniejsza różnica strukturalna wobec zwykłego kredytu.

W Fazie 1 część kapitałowa raty jest **stała i równa**, wyliczona na podstawie całego okresu
kredytowania (§2 ust. 17 warunków BGK):

```
część_kapitałowa = saldo_początkowe / łączna_liczba_miesięcy     [stała przez całą Fazę 1]
```

Część odsetkowa maleje z każdym miesiącem wraz ze spadkiem salda:

```
część_odsetkowa = Ks × 0,02 / 12                                 [malejąca]
```

Łączna rata płacona przez kredytobiorcę **maleje w czasie** — inaczej niż w standardowym
annuitet, gdzie pozostaje stała. To właśnie *raty malejące*.

Zwykły kredyt hipoteczny stosuje *raty równe* (annuitet). BK2% Faza 1 — nie.

Po zakończeniu Fazy 1 kredyt przechodzi na **standardowy annuitet** (raty równe) liczony od
pozostałego salda i pozostałych miesięcy (§2 ust. 17).

### 3b. Wzór na dopłatę BGK

Co miesiąc BGK wypłaca dopłatę D pomniejszającą ratę kredytobiorcy (§3 ust. 2 warunków BGK):

```
D = Ks × (W − 0,02) / 12
```

Gdzie:
- `Ks` = część kapitałowa kredytu pozostająca do spłaty w chwili ustalania raty
- `W`  = wskaźnik BGK — średnia ważona stopa nowo udzielanych kredytów hipotecznych ze stałą
         stopą × 0,9, ogłaszana kwartalnie. W praktyce zbliżona do stopy kontraktowej kredytu.
- `0,02` = 2%, czyli próg, który pokrywa kredytobiorca

Efektywny koszt odsetkowy kredytobiorcy:

```
odsetki kredytobiorcy  = Ks × 0,02 / 12           (jego część — 2%)
dopłata BGK            = Ks × (W − 0,02) / 12     (pokrywa spread do stopy rynkowej)
łączne odsetki         = Ks × W / 12              (≈ pełna stopa rynkowa)
```

**Obie części skalują się z Ks.** Gdy saldo spada — czy to przez regularne spłaty, czy przez
nadpłatę — zarówno koszt odsetkowy kredytobiorcy, jak i dopłata BGK maleją proporcjonalnie.

### 3c. Co kredytobiorca faktycznie płaci co miesiąc w Fazie 1

```
rata = część_kapitałowa + Ks × 0,02 / 12
     = saldo_początkowe / łączna_liczba_miesięcy + Ks × 0,02 / 12
```

Przykład (500 000 PLN, 25 lat, W ≈ 7,5%):

| Miesiąc | Ks (PLN)  | Część kapitałowa | Odsetki kredytobiorcy (2%) | Dopłata BGK (5,5%) | Rata kredytobiorcy |
|---------|-----------|------------------|----------------------------|--------------------|---------------------|
| 1       | 500 000   | 1 667            | 833                        | 2 292              | 2 500               |
| 60      | 400 000   | 1 667            | 667                        | 1 833              | 2 334               |
| 120     | 300 000   | 1 667            | 500                        | 1 375              | 2 167               |

Raty maleją przez Fazę 1, bo spada składnik odsetkowy. Płatności kredytobiorcy są zawsze niższe
niż przy zwykłym kredycie na tę samą kwotę.

---

## 4. Faza 2: po zakończeniu dopłat

Gdy 120. rata zgodna z harmonogramem zostanie zapłacona, dopłaty ustają. Kredyt jest
kontynuowany po pełnej stopie kontraktowej, w systemie równych rat (annuitet):

```
pozostałe_saldo ≈ saldo_początkowe × (1 − 120 / łączna_liczba_miesięcy)
               = 500 000 × (1 − 120/300) = 500 000 × 0,6 = 300 000 PLN (orientacyjnie)
```

Od tego momentu kredytobiorca płaci pełną stopę rynkową od każdej pozostałej złotówki.
Rata rośnie względem Fazy 1, bo:
1. Dopłata BGK znika
2. Przejście z *rat malejących* na *raty równe* (annuitet) zmienia strukturę płatności

---

## 5. Mechanika nadpłat

### 5a. 3-letni lock-in

Warunki programu (§4 ust. 6 pkt 10) stanowią, że wcześniejsza spłata części kredytu powoduje
**natychmiastowe wygaśnięcie wszystkich pozostałych dopłat**, chyba że spełniony jest
co najmniej jeden z poniższych warunków:

| Warunek | Zasada |
|---------|--------|
| Okres karencji | Nadpłata dokonana **po upływie 3 lat** od dnia udzielenia kredytu |
| Gwarancja BGK | Spłata dotyczy części objętej gwarancją BGK |
| Łączny limit kwotowy | Nadpłata + wkład własny kredytobiorcy łącznie ≤ 200 000 PLN |
| Miesięczny limit kwotowy | Nadpłata w danym miesiącu ≤ rata netto (po odjęciu dopłaty) |

W praktyce najistotniejszy jest warunek czasowy. Kredytobiorcy, którzy zaciągnęli BK2%
w 2023 roku, mogą bezpiecznie nadpłacać od **2026 roku**.

### 5b. Ile faktycznie oszczędzasz na nadpłacie

Ponieważ dopłata D skaluje się z Ks (§3 ust. 2), zmniejszenie Ks przez nadpłatę proporcjonalnie
zmniejsza dopłatę BGK. Dopłata to nie jest stały miesięczny grant — maleje wraz z saldem.

Konsekwencja: **kredytobiorca oszczędza odsetki tylko od swojej 2-procentowej części**,
a nie od pełnej stopy rynkowej.

```
nadpłata X podczas Fazy 1:
  oszczędzone odsetki miesięcznie  = X × 0,02 / 12          (tylko Twoja część — 2%)
  utracona dopłata BGK miesięcznie = X × (W − 0,02) / 12    (zawsze była częścią BGK, nie Twoją)
  efektywny zwrot z 1 PLN nadpłaty = 0,02 / 12 miesięcznie  = 2% rocznie
```

Dla porównania — w zwykłym kredycie nadpłata X oszczędza `X × 0,075 / 12` miesięcznie
(pełne 7,5%). Efektywny zwrot z tej samej nadpłaty jest 3–4× wyższy w zwykłym kredycie.

### 5c. Premia Fazy 2 — odroczona oszczędność

Nadpłata w Fazie 1 przynosi drugi, większy efekt: obniża saldo na wejściu do Fazy 2.
Ponieważ Faza 2 niesie pełną stopę (~7,5%), każda złotówka niższego salda w punkcie startu
Fazy 2 generuje oszczędności przy pełnej stopie.

```
oszczędność Fazy 1:  X × 0,02 × (miesiące_pozostałe_w_fazie_1 / 12)
oszczędność Fazy 2:  X × pełna_stopa × (miesiące_kredytu_po_fazie_2 / 12)  [orientacyjnie]
```

Proporcja tych dwóch efektów zależy całkowicie od tego, ile Fazy 1 jeszcze zostało:

| Pozostało Fazy 1 | Długość Fazy 2 | Dominująca oszczędność | Efektywny zwrot z nadpłaty |
|------------------|----------------|------------------------|---------------------------|
| 9 lat            | 6 lat          | Faza 1 (2%)            | ≈ 2–3%                    |
| 5 lat            | 10 lat         | Faza 2 (7,5%)          | ≈ 4–5%                    |
| 1 rok            | 14 lat         | Faza 2 (7,5%)          | ≈ 6–7%                    |

We wczesnym etapie kredytu nadpłata konkuruje z inwestowaniem przy efektywnym zwrocie 2%
— inwestowanie prawie zawsze wygrywa. Pod koniec okresu dopłat punkt opłacalności przesuwa się
i nadpłata może dorównać lub pobić 7% zwrotu brutto z inwestycji, zwłaszcza po podatku Belki.

### 5d. Miesięczny cap — bezpieczne mikronadpłaty

Warunek §4 ust. 6 pkt 10d tworzy ścieżkę bez ryzyka: każda dodatkowa płatność
nieprzekraczająca netto raty miesięcznej (po dopłacie) w danym miesiącu nie powoduje
utraty dopłat — nawet w oknie 3-letniego lock-inu.

```
bezpieczna_nadpłata_miesięczna ≤ rata_netto = część_kapitałowa + Ks × 0,02 / 12
```

To rzadko więcej niż 2 500–3 000 PLN miesięcznie we wczesnych latach kredytu na 500k.
Dla kredytobiorców chcących nadpłacać przed 2026 rokiem — ta ścieżka jest warta zamodelowania.

---

## 6. Porównanie: BK2% vs zwykły kredyt hipoteczny

| Właściwość | Zwykły kredyt | BK2% Faza 1 | BK2% Faza 2 |
|------------|---------------|-------------|-------------|
| Typ rat | Równe (annuitet) | Malejące (stały kapitał) | Równe (annuitet) |
| Efektywna stopa | Pełna (7–8%) | 2% | Pełna (7–8%) |
| Nadpłata oszczędza przy | Pełna stopa | Tylko 2% | Pełna stopa |
| Dopłata państwowa | Brak | BGK pokrywa spread | Brak |
| Ograniczenia nadpłat | Brak | 3-letni lock-in + wyjątki | Brak |
| Saldo po 10 latach | Wyższe (wolniejsza spłata na początku) | Niższe (stały kapitał) | — |

Uwaga: struktura *rat malejących* w Fazie 1 sprawia, że kredytobiorca spłaca saldo **szybciej**
niż w annuitet przez pierwsze 10 lat — część kapitałowa jest taka sama co miesiąc, niezależnie
od poziomu odsetek, zamiast być „wypierana" przez odsetki jak w annuitet.

---

## 7. Optymalna strategia

### Reguła 1: Przed 3. rokiem — nie nadpłacaj powyżej miesięcznego capu

Chyba że nadpłata mieści się w limicie łącznym (≤200k razem z wkładem własnym), każda
wcześniejsza spłata zabija dopłaty warte tysiące złotych miesięcznie. Ścieżka miesięcznego
capu jest niskodźwigniowa — warta rozważenia tylko przy nadwyżce płynności bez lepszej opcji.

### Reguła 2: Po 3. roku — porównaj z tym, co faktycznie zarobisz

Efektywny zwrot z nadpłaty to nie 2% i nie 7,5% — to stopa wypadkowa:

```
efektywny_zwrot = (miesiące_fazy_1 × 2% + miesiące_fazy_2 × pełna_stopa) / łączne_miesiące_pozostałe
```

Porównaj to z `compare_return × (1 − 0,19)` (inwestycja na rachunku opodatkowanym, po Belce).
W IKE porównuj do zwrotu brutto `compare_return` — brak podatku Belki.

### Reguła 3: Timing ważniejszy niż kwota

Nadpłata 50 000 PLN z 9 latami dopłat przed sobą daje mniej więcej połowę oszczędności
odsetkowych tej samej nadpłaty z 1 rokiem dopłat przed sobą. Jeśli Faza 2 zbliża się
szybko, czekanie i nadpłata tuż przed Fazą 2 może pobić nadpłatę teraz.

### Reguła 4: Zaplanuj skok raty przy przejściu do Fazy 2

Na początku Fazy 2 rata miesięczna znacząco rośnie: znika dopłata + przejście na annuitet.
Planowanie płynności powinno uwzględniać ten skok. Nadpłata przed Fazą 2 bezpośrednio
obniża ratę Fazy 2.

---

## 8. Co liczy `bk2_overpayment()`

Kalkulator implementuje model dwufazowy:

1. **Symulacja Fazy 1** (od dziś do `subsidy_end`):
   - Amortyzacja *ratami malejącymi* (`część_kapitałowa = saldo / pozostałe_miesiące`)
   - Wariant bez nadpłaty i z nadpłatą
   - Oszczędności odsetkowe przy `monthly_rate = 0,02/12`

2. **Symulacja Fazy 2** (od `subsidy_end` do końca kredytu):
   - Przejście na annuitet przy `full_monthly_rate`
   - Inne saldo startowe zależnie od wariantu nadpłaty
   - Oszczędności odsetkowe przy `full_monthly_rate`

3. **Dane wyjściowe**:
   - `interest_saved_phase1` i `interest_saved_phase2` (osobno — pełna transparentność)
   - `months_shortened` (łącznie)
   - `equivalent_annual_return` (wypadkowy, zannualizowany na cały pozostały okres)
   - `subsidy_at_risk` (True jeśli nadpłata jest w 3-letnim lock-inie i przekracza miesięczny cap)
   - `recommendation` (inwestuj / nadpłacaj) wobec `compare_return`

**Parametry wyciągane przez LLM z pytania lub profilu:**
- `balance` — aktualne pozostałe saldo główne (PLN)
- `monthly_rate` — efektywna stopa w okresie dopłat = `0,02/12` ≈ 0,001667 (zawsze dla BK2%)
- `full_monthly_rate` — pełna stopa kontraktowa / 12 (WIRON + marża; odczytywana z profilu)
- `overpayment` — jednorazowa lub miesięczna nadpłata (PLN)
- `subsidy_end` — data ISO, kiedy spłacona zostanie 120. rata
- `loan_end` — data ISO ostatniej planowej raty
- `origination_date` — data ISO udzielenia kredytu (do sprawdzenia lock-inu)
- `own_contribution` — wkład własny przy udzieleniu (do sprawdzenia limitu 200k)
- `compare_return` — oczekiwany roczny zwrot brutto z inwestycji (domyślnie `0,07`)
- `in_ike` — czy inwestycja alternatywna jest w IKE (brak Belki, domyślnie `False`)

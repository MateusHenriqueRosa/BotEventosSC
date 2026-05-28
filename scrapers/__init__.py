from .helpers import criar_driver, resetar_driver, cancelavel_sleep
from .ingresso_nacional import buscar_ingressonacional
from .blueticket import buscar_blueticket
from .guicheweb import buscar_guicheweb
from .pensanoevento import buscar_pensanoevento
from .minhaentrada import buscar_minhaentrada
from .bilheteriadigital import buscar_bilheteriadigital
from .aquitemingressos import buscar_aquitemingressos
from .ingressodigital import buscar_ingressodigital
from .eticketcenter import buscar_eticketcenter

SITES = [
    ("Ingresso Nacional", "ingressonacional.com.br"),
    ("Blueticket", "blueticket.com.br"),
    ("Guichê Web", "guicheweb.com.br"),
    ("Pensa no Evento", "pensanoevento.com.br"),
    ("Minha Entrada", "minhaentrada.com.br"),
    ("Bilheteria Digital", "bilheteriadigital.com"),
    ("Aqui Tem Ingressos", "aquitemingressos.com.br"),
    ("Ingresso Digital", "ingressodigital.com"),
    ("eTicket Center", "eticketcenter.com.br"),
]

# Disclaimer – famkit

*(Italiano più sotto.)*

**famkit is provided "as is", without warranty of any kind, express or implied, under the [MIT License](LICENSE).
The authors and contributors accept no responsibility and no liability for any damage, loss or consequence of
any kind arising from using, installing, configuring or being unable to use this software** — including, without
limitation, loss or corruption of data, disclosure of personal data, security breaches, unauthorised access,
failed backups, emails not delivered, or any decision taken on the basis of what the software does.

- **The code was written with the help of an AI assistant** (Anthropic's Claude) and checked with automated
  tests. It has not been audited. Review it before trusting it with real data or exposing it to the internet.
- **It handles security-sensitive things**: sign-in with OpenID Connect providers, the link between the apps and
  Wombat, the keys the servers use to talk to each other, and copies of the databases. A mistake here, or a key that
  leaks, can expose the data of every app that uses it. Keep the keys secret, use HTTPS, and keep the apps updated.
- **Backups are not guaranteed**: the copies famkit makes live next to the database they copy. Keep copies
  elsewhere too, and check from time to time that you can actually restore them.
- **famkit is not an application on its own**: it is used by Wombat, Kooka, Wallaby and Pelican, whose own
  disclaimers apply as well. Whoever runs those apps is responsible for them and for the data in them (and, when
  other people use them, is the data controller under the applicable law, e.g. the GDPR).
- No support, maintenance or availability is promised.

---

# Esclusione di responsabilità – famkit

**famkit è fornito "così com'è", senza alcuna garanzia, esplicita o implicita, secondo la [licenza MIT](LICENSE).
Autori e contributori non si assumono alcuna responsabilità per danni, perdite o conseguenze di qualsiasi tipo
derivanti dall'uso, dall'installazione, dalla configurazione o dall'impossibilità di usare questo software** —
tra cui, a titolo di esempio, perdita o danneggiamento di dati, diffusione di dati personali, violazioni della
sicurezza, accessi non autorizzati, backup non riusciti, email non consegnate, o decisioni prese in base a ciò che
il software fa.

- **Il codice è stato scritto con l'aiuto di un assistente di intelligenza artificiale** (Claude di Anthropic) e
  verificato con test automatici. Non è stato sottoposto a revisione indipendente. Controllalo prima di affidargli
  dati reali o di esporlo su internet.
- **Gestisce cose delicate per la sicurezza**: l'accesso con i provider OpenID Connect, il collegamento tra le app e
  Wombat, le chiavi con cui i server si parlano, le copie dei database. Un errore qui, o una chiave che finisce in mani
  sbagliate, può esporre i dati di tutte le app che lo usano. Tieni segrete le chiavi, usa HTTPS e tieni aggiornate
  le app.
- **I backup non sono garantiti**: le copie fatte da famkit stanno accanto al database che copiano. Tienine anche
  altrove e verifica ogni tanto di riuscire davvero a ripristinarle.
- **famkit non è un'applicazione a sé**: lo usano Wombat, Kooka, Wallaby e Pelican, per cui valgono anche le loro
  esclusioni di responsabilità. Chi installa quelle app ne è responsabile, insieme ai dati che contengono (e, se le
  fa usare ad altre persone, è il titolare del trattamento secondo la normativa applicabile, per esempio il GDPR).
- Non è promesso alcun supporto, manutenzione o disponibilità del servizio.

ez csak cirkadián adjusztment nem igazi bruszt tesomsz.

setup:
pityon3.12n fut de 3.9 elvileg elég(?)  
Csinalsz magadnak discord botot meg tokent hozza https://discord.com/developers/applications  
Meghivod sajat szerverre  
.envbe beirod a tokent meg egy channel idt ahova irja h na re az .env-example alapján  
Requirementset felrakod  
Elinditod a main.py-t 
bot-baratok (opcionalis):  
.env-be BOT_FRIENDS=<bot user id, vesszovel tobbet> — az itt felsorolt botok taggelhetik/replyzhetik a ruinbotot es valaszt kapnak (pinggel), minden mas bot tovabbra is ignoralva. A bot-barat szovegebol NEM tanul a markov.
linkjavitas ki/be (opcionalis):  
`r!linkfixer ki` — az egesz szerveren kikapcsolja (Manage Server jog kell), `r!linkfixer ki csatorna` — csak abban a csatornaban (Manage Channels jog kell), `r!linkfixer be` visszakapcsolja, `r!linkfixer allapot` megmutatja. A beallitas a usr/linkfixer.json-ben marad meg.
A csatornaszintu allapot a szerver es thread eseten a szulocsatorna tiltasat is jelzi; a `be csatorna` ezeket nem irja felul.
A Facebook-linkeket (facebook.com, www/m/mbasic/web valtozatok) facebed.com linkekre javitja, az eredeti utvonallal es query parameterekkel.

(*
	Colada Vorauswahl – Mac-App für einen Bilderordner (ohne Capture One)
	Picture Colada · Version 0.1

	Ordner wählen (oder auf das App-Symbol ziehen) -> Analyse -> Sterne als XMP-Dateien neben die
	Bilder. Capture One übernimmt die Sterne beim Import automatisch. Zusätzlich gibt es einen
	Prüfbericht (HTML) mit Begründung pro Bild.

	Wird von install.sh nach ~/Applications/Colada Vorauswahl.app kompiliert.
*)

use AppleScript version "2.4"
use scripting additions

property appName : "Colada Vorauswahl"
property supportDir : "Library/Application Support/ColadaCull/"

on run
	set f to choose folder with prompt "Ordner mit den Fotos des Shootings wählen:"
	my process(POSIX path of f)
end run

on open droppedItems
	repeat with d in droppedItems
		set p to POSIX path of d
		if p ends with "/" then my process(p)
	end repeat
end open

on process(folderPath)
	set homePath to POSIX path of (path to home folder)
	set baseDir to homePath & supportDir
	set pythonBin to baseDir & "venv/bin/python"
	set engineDir to baseDir & "engine"
	try
		do shell script "test -x " & quoted form of pythonBin
	on error
		display alert appName message ("Die Analyse-Engine ist nicht installiert. Bitte install.sh ausführen.") as critical
		return
	end try

	set modeLabels to {"Automatisch (gemischtes Shooting)", "Produkt / Detail", "Prozess / Reportage", "Menschen / Porträt", "Architektur / Gebäude"}
	set modeKeys to {"auto", "produkt", "prozess", "people", "architektur"}
	set pickedMode to choose from list modeLabels with title appName with prompt "Worum geht es in diesem Shooting?" default items {item 1 of modeLabels} OK button name "Weiter" cancel button name "Abbrechen"
	if pickedMode is false then return
	set modeKey to my lookup(item 1 of pickedMode, modeLabels, modeKeys)

	set strictLabels to {"Locker – lieber etwas mehr behalten", "Normal", "Streng – nur das Beste"}
	set strictKeys to {"locker", "normal", "streng"}
	set pickedStrict to choose from list strictLabels with title appName with prompt "Wie streng soll aussortiert werden?" default items {item 2 of strictLabels} OK button name "Weiter" cancel button name "Abbrechen"
	if pickedStrict is false then return
	set strictKey to my lookup(item 1 of pickedStrict, strictLabels, strictKeys)

	set writeChoice to button returned of (display dialog "Ergebnis als Sterne in XMP-Dateien neben die Bilder schreiben?" & return & return & "(Capture One liest die Sterne beim Import. Vorhandene XMP-Dateien werden ergänzt, nicht ersetzt.)" buttons {"Abbrechen", "Nur Bericht", "XMP schreiben"} default button 3 with title appName)
	if writeChoice is "Abbrechen" then return

	set stamp to do shell script "date +%Y%m%d-%H%M%S"
	set workDir to baseDir & "runs/" & stamp & "/"
	do shell script "mkdir -p " & quoted form of workDir
	set progressFile to workDir & "fortschritt.txt"
	set reportFile to workDir & "bericht.html"
	set logFile to workDir & "log.txt"
	set xmpArg to ""
	if writeChoice is "XMP schreiben" then set xmpArg to " --xmp"

	set cmd to "cd " & quoted form of engineDir & " && nohup " & quoted form of pythonBin & " -m colada_cull --folder " & quoted form of folderPath & ¬
		" --progress-file " & quoted form of progressFile & " --report " & quoted form of reportFile & ¬
		" --mode " & modeKey & " --strictness " & strictKey & xmpArg & " > " & quoted form of logFile & " 2>&1 & echo $!"
	set pid to do shell script cmd

	set progress description to appName & ": Bilder analysieren"
	set progress total steps to -1
	set progress completed steps to 0
	set lastText to ""
	repeat
		delay 1
		try
			set lastText to do shell script "cat " & quoted form of progressFile
		end try
		if lastText starts with "fertig" or lastText starts with "fehler" then exit repeat
		try
			set AppleScript's text item delimiters to "/"
			set doneCount to (text item 1 of lastText) as integer
			set allCount to (text item 2 of lastText) as integer
			set AppleScript's text item delimiters to ""
			set progress total steps to allCount
			set progress completed steps to doneCount
			set progress additional description to (doneCount as text) & " von " & allCount & " Bildern"
		on error
			set AppleScript's text item delimiters to ""
		end try
		try
			do shell script "kill -0 " & pid
		on error
			delay 1
			try
				set lastText to do shell script "cat " & quoted form of progressFile
			end try
			if lastText starts with "fertig" then exit repeat
			set logTail to ""
			try
				set logTail to do shell script "tail -n 15 " & quoted form of logFile
			end try
			display alert appName message ("Die Analyse wurde unerwartet beendet." & return & return & logTail) as critical
			return
		end try
	end repeat
	if lastText starts with "fehler" then
		display alert appName message (text 8 thru -1 of lastText) as warning
		return
	end if
	set msg to (text 8 thru -1 of lastText) & return & return & "Vorauswahl = 3 Sterne · Alternative = 1 Stern · aussortiert = 0 Sterne."
	set btn to button returned of (display dialog msg buttons {"Ordner zeigen", "Prüfbericht öffnen"} default button 2 with title appName with icon note)
	if btn is "Prüfbericht öffnen" then
		do shell script "open " & quoted form of reportFile
	else
		do shell script "open " & quoted form of folderPath
	end if
end process

on lookup(theLabel, labels, keys)
	repeat with i from 1 to count of labels
		if item i of labels is theLabel then return item i of keys
	end repeat
	return item 1 of keys
end lookup

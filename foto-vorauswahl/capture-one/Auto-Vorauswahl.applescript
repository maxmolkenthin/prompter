(*
	Auto-Vorauswahl (Colada Cull) – Capture One Script
	Picture Colada · Version 0.1

	Analysiert die ausgewählten Bilder (oder alle Bilder der aktuellen Sammlung) und vergibt
	Sterne + Farbmarkierung direkt in Capture One:
	  Auswahl      = ★★★ + Grün
	  Alternative  = ★   (keine Farbe)
	  Aussortiert  = 0 Sterne + Rot   (unscharf, verwackelt, Augen zu, Fehlauslösung)

	Installation: über install.sh (legt dieses Script nach ~/Library/Scripts/Capture One Scripts/).
	Danach in Capture One: Menü Scripts > Update Script Menu, dann Scripts > Auto-Vorauswahl.
*)

use AppleScript version "2.4"
use scripting additions

property appName : "Auto-Vorauswahl"
property supportDir : "Library/Application Support/ColadaCull/"

on run
	set homePath to POSIX path of (path to home folder)
	set baseDir to homePath & supportDir
	set pythonBin to baseDir & "venv/bin/python"
	set engineDir to baseDir & "engine"

	-- Engine vorhanden?
	try
		do shell script "test -x " & quoted form of pythonBin & " && test -d " & quoted form of engineDir
	on error
		display alert appName message ("Die Analyse-Engine ist nicht installiert." & return & return & "Bitte install.sh aus dem Ordner foto-vorauswahl ausführen.") as critical
		return
	end try

	-- Capture One bereit?
	tell application "Capture One" to set docCount to count of documents
	if docCount is 0 then
		display alert appName message ("Bitte zuerst eine Session oder einen Katalog in Capture One öffnen.") as warning
		return
	end if
	tell application "Capture One" to set theVariants to selected variants

	if (count of theVariants) < 2 then
		tell application "Capture One" to tell current document
			set allVariants to every variant of current collection
		end tell
		set n to count of allVariants
		if n is 0 then
			display alert appName message ("In der aktuellen Sammlung sind keine Bilder.") as warning
			return
		end if
		set answer to button returned of (display dialog "Es sind keine Bilder ausgewählt." & return & return & "Alle " & n & " Bilder der aktuellen Sammlung analysieren?" buttons {"Abbrechen", "Alle analysieren"} default button 2 with title appName with icon note)
		if answer is "Abbrechen" then return
		set theVariants to allVariants
	end if
	set total to count of theVariants

	-- Einstellungen
	set modeLabels to {"Automatisch (gemischtes Shooting)", "Produkt / Detail", "Prozess / Reportage", "Menschen / Porträt", "Architektur / Gebäude"}
	set modeKeys to {"auto", "produkt", "prozess", "people", "architektur"}
	set pickedMode to choose from list modeLabels with title appName with prompt "Worum geht es bei diesen " & total & " Bildern?" default items {item 1 of modeLabels} OK button name "Weiter" cancel button name "Abbrechen"
	if pickedMode is false then return
	set modeKey to my lookup(item 1 of pickedMode, modeLabels, modeKeys)

	set strictLabels to {"Locker – lieber etwas mehr behalten", "Normal", "Streng – nur das Beste"}
	set strictKeys to {"locker", "normal", "streng"}
	set pickedStrict to choose from list strictLabels with title appName with prompt "Wie streng soll aussortiert werden?" default items {item 2 of strictLabels} OK button name "Weiter" cancel button name "Abbrechen"
	if pickedStrict is false then return
	set strictKey to my lookup(item 1 of pickedStrict, strictLabels, strictKeys)

	set overwriteChoice to button returned of (display dialog "Bereits vorhandene Sterne/Farben:" buttons {"Abbrechen", "Nicht anfassen", "Überschreiben"} default button 2 with title appName)
	if overwriteChoice is "Abbrechen" then return
	set keepExisting to (overwriteChoice is "Nicht anfassen")

	-- Arbeitsdateien
	set stamp to do shell script "date +%Y%m%d-%H%M%S"
	set workDir to baseDir & "runs/" & stamp & "/"
	do shell script "mkdir -p " & quoted form of workDir
	set listFile to workDir & "pfade.txt"
	set resultFile to workDir & "ergebnis.tsv"
	set progressFile to workDir & "fortschritt.txt"
	set reportFile to workDir & "bericht.html"
	set logFile to workDir & "log.txt"

	-- Pfade einsammeln
	set progress total steps to total
	set progress completed steps to 0
	set progress description to appName & ": Bilder einlesen"
	set pathLines to {}
	repeat with i from 1 to total
		set p to ""
		try
			tell application "Capture One" to set p to path of parent image of (item i of theVariants)
		end try
		set end of pathLines to p
		if i mod 25 is 0 then set progress completed steps to i
	end repeat
	set AppleScript's text item delimiters to linefeed
	set listText to pathLines as text
	set AppleScript's text item delimiters to ""
	my writeUTF8(listFile, listText & linefeed)

	-- Analyse im Hintergrund starten, Fortschritt abfragen
	set cmd to "cd " & quoted form of engineDir & " && nohup " & quoted form of pythonBin & " -m colada_cull --list " & quoted form of listFile & ¬
		" --results " & quoted form of resultFile & " --progress-file " & quoted form of progressFile & ¬
		" --report " & quoted form of reportFile & " --mode " & modeKey & " --strictness " & strictKey & ¬
		" > " & quoted form of logFile & " 2>&1 & echo $!"
	set pid to do shell script cmd

	set progress description to appName & ": Bilder analysieren"
	set progress completed steps to 0
	set finished to false
	set lastChange to current date
	set lastText to ""
	repeat until finished
		delay 1
		set progText to ""
		try
			set progText to do shell script "cat " & quoted form of progressFile
		end try
		if progText is not lastText then
			set lastText to progText
			set lastChange to current date
		end if
		if progText starts with "fertig" or progText starts with "fehler" then
			set finished to true
		else
			try
				set AppleScript's text item delimiters to "/"
				set doneCount to (text item 1 of progText) as integer
				set allCount to (text item 2 of progText) as integer
				set AppleScript's text item delimiters to ""
				set progress total steps to allCount
				set progress completed steps to doneCount
				set progress additional description to (doneCount as text) & " von " & allCount & " Bildern analysiert"
			on error
				set AppleScript's text item delimiters to ""
			end try
			-- läuft der Prozess noch?
			try
				do shell script "kill -0 " & pid
			on error
				delay 1
				try
					set progText to do shell script "cat " & quoted form of progressFile
				end try
				if not (progText starts with "fertig") then
					set logTail to ""
					try
						set logTail to do shell script "tail -n 15 " & quoted form of logFile
					end try
					display alert appName message ("Die Analyse wurde unerwartet beendet." & return & return & logTail) as critical
					return
				end if
				set finished to true
			end try
		end if
	end repeat

	if lastText starts with "fehler" then
		display alert appName message ("Analyse fehlgeschlagen: " & lastText) as critical
		return
	end if

	-- Ergebnisse in Capture One eintragen
	set resultLines to paragraphs of (read (POSIX file resultFile) as «class utf8»)
	set progress description to appName & ": Sterne und Farben setzen"
	set progress total steps to total
	set progress completed steps to 0
	set setCount to 0
	set skipCount to 0
	set AppleScript's text item delimiters to tab
	repeat with i from 1 to total
		if i > (count of resultLines) then exit repeat
		set fields to text items of (item i of resultLines)
		if (count of fields) ≥ 3 and (item 1 of fields) is not "-" then
			set newRating to (item 1 of fields) as integer
			set newColor to (item 2 of fields) as integer
			set v to item i of theVariants
			try
				tell application "Capture One"
					set doIt to true
					if keepExisting then
						if (rating of v) > 0 or (color tag of v) > 0 then set doIt to false
					end if
					if doIt then
						set rating of v to newRating
						set color tag of v to newColor
					end if
				end tell
				if doIt then
					set setCount to setCount + 1
				else
					set skipCount to skipCount + 1
				end if
			end try
		end if
		if i mod 10 is 0 then set progress completed steps to i
	end repeat
	set AppleScript's text item delimiters to ""
	set progress completed steps to total

	set summary to text 8 thru -1 of lastText -- "fertig/" abschneiden
	set msg to summary & return & return & setCount & " Bilder markiert"
	if skipCount > 0 then set msg to msg & ", " & skipCount & " mit vorhandener Bewertung nicht verändert"
	set msg to msg & "." & return & return & "Grün + 3 Sterne = Vorauswahl · Rot = aussortiert (nichts wird gelöscht)." & return & "Tipp: In Capture One nach Farbmarkierung Grün filtern."
	set btn to button returned of (display dialog msg buttons {"Prüfbericht öffnen", "Fertig"} default button 2 with title appName with icon note)
	if btn is "Prüfbericht öffnen" then do shell script "open " & quoted form of reportFile
end run

on lookup(theLabel, labels, keys)
	repeat with i from 1 to count of labels
		if item i of labels is theLabel then return item i of keys
	end repeat
	return item 1 of keys
end lookup

on writeUTF8(posixPath, theText)
	set f to open for access (POSIX file posixPath) with write permission
	try
		set eof of f to 0
		write theText to f as «class utf8»
		close access f
	on error e
		close access f
		error e
	end try
end writeUTF8

"""Patch 2: Ajoute le bouton d'onglet Tailor dans les onglets du modal."""

with open("static/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Le marqueur exact : fermeture du btn CV puis fermeture du div tabs
MARKER = '</button>\n            </div>\n\n            <div class="modal-body">'

REPLACEMENT = (
    '</button>\n'
    '                <button class="btn btn-outline modal-tab-btn" id="tab-btn-tailor"'
    ' onclick="switchModalTab(\'tailor\')"'
    ' style="padding: 6px 14px; font-size: 12.5px; font-weight: 600;'
    ' background: linear-gradient(135deg, #f0fdf4, #dcfce7);'
    ' border-color: #86efac; color: #15803d;">\n'
    '                    <i class="fa-solid fa-wand-magic-sparkles"></i>'
    ' CV &amp; Lettre PDF\n'
    '                </button>\n'
    '            </div>\n\n'
    '            <div class="modal-body">'
)

if MARKER in content:
    content = content.replace(MARKER, REPLACEMENT, 1)
    print("OK: Bouton onglet Tailor inséré")
else:
    print("WARN: Marqueur non trouvé, recherche debug...")
    # Find where tabs div ends
    idx = content.find('tab-btn-cv')
    snippet = content[idx:idx+500]
    print("Snippet autour de tab-btn-cv:")
    for i, line in enumerate(snippet.split('\n')):
        print(f"  {i}: {repr(line)}")

with open("static/index.html", "w", encoding="utf-8") as f:
    f.write(content)
print("Sauvegardé.")

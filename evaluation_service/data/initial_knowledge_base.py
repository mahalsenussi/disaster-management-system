"""
Initial Knowledge Base Data
Humanitarian information for LRC chatbot
"""

INITIAL_KNOWLEDGE_ENTRIES = [
    # LRC Organization
    {
        'category': 'lrc_organization',
        'title': 'Libyan Red Crescent - Overview',
        'content': '''The Libyan Red Crescent (LRC) is the national humanitarian society of Libya, part of the International Red Cross and Red Crescent Movement. It provides emergency assistance, disaster relief, and health services throughout Libya. The LRC operates under the Fundamental Principles of the Red Cross and Red Crescent: Humanity, Impartiality, Neutrality, Independence, Voluntary Service, Unity, and Universality.''',
        'source': 'LRC',
        'source_url': 'https://lrc.org.ly',
        'tags': ['overview', 'organization', 'principles'],
        'priority': 10
    },
    {
        'category': 'lrc_organization',
        'title': 'LRC Mission',
        'content': '''The Libyan Red Crescent mission is to prevent and alleviate human suffering wherever it may be found, to protect life and health, and to ensure respect for the human being. It promotes mutual understanding, friendship, cooperation, and lasting peace among all peoples.''',
        'source': 'LRC',
        'tags': ['mission', 'values'],
        'priority': 10
    },
    
    # Humanitarian Principles
    {
        'category': 'humanitarian_principles',
        'title': 'Fundamental Principles of the Red Cross',
        'content': '''The Fundamental Principles of the International Red Cross and Red Crescent Movement are:
1. Humanity: The Red Cross, born of a desire to bring assistance without discrimination to the wounded on the battlefield, endeavors—in its international and national capacity—to prevent and alleviate human suffering wherever it may be found.
2. Impartiality: It makes no discrimination as to nationality, race, religious beliefs, class, or political opinions.
3. Neutrality: In order to continue to enjoy the confidence of all, the Movement may not take sides in hostilities or engage at any time in controversies of a political, racial, religious, or ideological nature.
4. Independence: The Movement is independent.
5. Voluntary Service: It is a voluntary relief movement not prompted in any manner by desire for gain.
6. Unity: There can be only one Red Cross or one Red Crescent in any one country.
7. Universality: The International Red Cross and Red Crescent Movement, in which all Societies have equal status and share equal responsibilities and duties in helping each other, is worldwide.''',
        'source': 'IFRC',
        'source_url': 'https://www.ifrc.org',
        'tags': ['principles', 'fundamental', 'ifrc'],
        'priority': 10
    },
    
    # Emergency Response
    {
        'category': 'emergency_response',
        'title': 'Emergency Response Protocols',
        'content': '''LRC emergency response follows international standards:
- Rapid assessment within 24-48 hours of disaster
- Immediate provision of food, water, shelter, and medical aid
- Coordination with local authorities and international partners
- Registration and tracing services for separated families
- Psychological support for affected populations
- Restoration of family links
- Cash assistance where appropriate''',
        'source': 'LRC',
        'tags': ['emergency', 'response', 'protocols'],
        'priority': 9
    },
    
    # First Aid
    {
        'category': 'first_aid',
        'title': 'First Aid Services',
        'content': '''LRC provides first aid training and services including:
- Basic first aid courses for volunteers and community members
- First aid stations at public events
- Emergency first aid response teams
- Ambulance services in major cities
- First aid kits distribution
- CPR and AED training
- Basic life support training''',
        'source': 'LRC',
        'tags': ['first_aid', 'training', 'medical'],
        'priority': 8
    },
    
    # Contact Information
    {
        'category': 'contact_information',
        'title': 'LRC Main Office - Tripoli',
        'content': '''Libyan Red Crescent National Headquarters
Location: Tripoli, Libya
The main office coordinates all LRC activities nationwide and serves as the primary point of contact for international partners and coordination with the IFRC and ICRC.''',
        'source': 'LRC',
        'tags': ['contact', 'headquarters', 'tripoli'],
        'priority': 10
    },
    {
        'category': 'contact_information',
        'title': 'LRC Emergency Contact',
        'content': '''For emergency assistance, contact the Libyan Red Crescent emergency hotline. In case of disasters or emergencies, LRC volunteers and emergency response teams are mobilized through the national coordination center.''',
        'source': 'LRC',
        'tags': ['emergency', 'contact', 'hotline'],
        'priority': 10
    },
    
    # Partners
    {
        'category': 'partners',
        'title': 'International Federation of Red Cross (IFRC)',
        'content': '''The International Federation of Red Cross and Red Crescent Societies (IFRC) is the world's largest humanitarian network, reaching 150 million people each year through 192 member National Societies. The IFRC coordinates and directs international assistance to LRC during disasters and crises, and supports capacity building and development programs.''',
        'source': 'IFRC',
        'source_url': 'https://www.ifrc.org',
        'tags': ['partner', 'ifrc', 'international'],
        'priority': 9
    },
    {
        'category': 'partners',
        'title': 'International Committee of the Red Cross (ICRC)',
        'content': '''The International Committee of the Red Cross (ICRC) is an impartial, neutral and independent organization whose exclusively humanitarian mission is to protect the lives and dignity of victims of armed conflict and other situations of violence and to provide them with assistance. The ICRC works closely with LRC in protection, detention visits, and restoring family links.''',
        'source': 'ICRC',
        'source_url': 'https://www.icrc.org',
        'tags': ['partner', 'icrc', 'protection'],
        'priority': 9
    },
    {
        'category': 'partners',
        'title': 'United Nations Humanitarian Agencies',
        'content': '''LRC coordinates with UN agencies including:
- UNOCHA (Office for the Coordination of Humanitarian Affairs) - Overall humanitarian coordination
- UNHCR (UN Refugee Agency) - Refugee and displacement support
- WHO (World Health Organization) - Health emergencies and medical support
- UNICEF (UN Children's Fund) - Child protection and education
- WFP (World Food Programme) - Food security and logistics
- IOM (International Organization for Migration) - Migration and displacement''',
        'source': 'UN',
        'source_url': 'https://www.un.org',
        'tags': ['partner', 'un', 'coordination'],
        'priority': 8
    },
    
    # Disaster Management
    {
        'category': 'disaster_management',
        'title': 'Disaster Risk Reduction',
        'content': '''LRC disaster risk reduction activities include:
- Community-based disaster risk management
- Early warning systems
- Disaster preparedness training
- Risk assessment and mapping
- Community resilience building
- School safety programs
- Climate change adaptation initiatives''',
        'source': 'LRC',
        'tags': ['disaster', 'risk_reduction', 'preparedness'],
        'priority': 8
    },
    
    # Training
    {
        'category': 'training',
        'title': 'Volunteer Training Programs',
        'content': '''LRC offers comprehensive training for volunteers:
- Introduction to Red Cross Red Crescent Movement
- First aid and emergency response
- Disaster management
- Psychosocial support
- Restoring family links
- International humanitarian law basics
- Community engagement and mobilization
- Safety and security in humanitarian operations''',
        'source': 'LRC',
        'tags': ['training', 'volunteers', 'capacity'],
        'priority': 7
    },
    
    # Volunteers
    {
        'category': 'volunteers',
        'title': 'Volunteer Management',
        'content': '''LRC volunteers are the backbone of humanitarian response in Libya. Volunteers receive training, equipment, and support to carry out their duties safely and effectively. Volunteer management includes recruitment, training, deployment, and recognition of volunteer contributions to humanitarian work.''',
        'source': 'LRC',
        'tags': ['volunteers', 'management', 'recruitment'],
        'priority': 7
    },
]

# Additional humanitarian sources for reference
HUMANITARIAN_SOURCES = {
    'IFRC': 'https://www.ifrc.org',
    'ICRC': 'https://www.icrc.org',
    'UNOCHA': 'https://www.unocha.org',
    'UNHCR': 'https://www.unhcr.org',
    'WHO': 'https://www.who.int',
    'UNICEF': 'https://www.unicef.org',
    'WFP': 'https://www.wfp.org',
    'IOM': 'https://www.iom.int',
    'LRC': 'https://lrc.org.ly',
}

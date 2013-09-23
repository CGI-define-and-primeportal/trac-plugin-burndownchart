$(document).ready(function(){
      // Redraw the burndown on milestone page with new metric via AJAX

    $('#unit-effort-question').click(function() {
      $('#unit-effort-dialog').dialog({
        title: 'More Information - Unit Effort',
        width: 400,
        modal: true,
        buttons: {
          'Close': function() {
            $(this).dialog('close');
          }
        }
      });
    });

    $('#work-day-question').click(function() {
      $('#work-day-dialog').dialog({
        title: 'More Information - Working Days',
        width: 400,
        modal: true,
        buttons: {
          'Close': function() {
            $(this).dialog('close');
          }
        }
      });
    });

    $('#ideal-curve-question').click(function() {
      $('#ideal-curve-dialog').dialog({
        title: 'More Information - Idea Curve',
        width: 400,
        modal: true,
        buttons: {
          'Close': function() {
            $(this).dialog('close');
          }
        }
      });
    });

});